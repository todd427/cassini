"""Galileo OSNMA local cryptographic verifier and EvidenceConnector.

Parses genuine recorded Septentrio SBF (`GALRawINAV` Block 4023 + `ReceiverSetup`
Block 5902) together with official European GNSS Service Centre (GSC) Merkle Tree
and Public Key XML files, performing full local 4-layer Galileo OSNMA SIS ICD v1.1
cryptographic verification:

1. GSC Merkle Tree SHA-256 proof from PublicKey to Merkle Root (x_{4,0}).
2. ECDSA P-256 / SHA-256 digital signature verification over NMA_Header || DSM-KROOT.
3. TESLA one-way SHA-256 key chain verification back to KROOT.
4. HMAC-SHA-256 Tag0 (ADKD=0) verification over Galileo I/NAV Word Types 1-5
   (549-bit ephemeris, clock, ionospheric/BGD, and health/DVS navigation data).

Specialist dependency `ecdsa` is imported lazily so core EIP stays isolated
from GNSS cryptographic libraries.
"""

from __future__ import annotations

import hashlib
import hmac
import struct
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from connectors.base import ConnectorMetadata
from core.integrity import compute_file_sha256
from core.models import Evidence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GALILEO_DIR = REPO_ROOT / "sample_data" / "raw" / "galileo"
DEFAULT_SBF_PATH = DEFAULT_GALILEO_DIR / "osnma_new_config.sbf"
DEFAULT_MERKLE_PATH = DEFAULT_GALILEO_DIR / "OSNMA_MerkleTree.xml"
DEFAULT_PUBKEY_PATH = DEFAULT_GALILEO_DIR / "OSNMA_PublicKey.xml"
DEFAULT_SBF_SOURCE_URL = (
    "https://raw.githubusercontent.com/Algafix/OSNMA/master/"
    "tests/scenarios/new_live_config/osnma_new_config.sbf"
)

# GPS/Galileo epoch (1980-01-06T00:00:00Z); UTC-GST leap seconds = 18s (since 2017-01-01)
_GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)
_GPS_UTC_LEAP_SECONDS = 18

_NB_DK_MAP = {1: 7, 2: 8, 3: 9, 4: 10, 5: 11, 6: 12, 7: 13, 8: 14}
_KS_MAP = {0: 96, 1: 104, 2: 112, 3: 120, 4: 128, 5: 160, 6: 192, 7: 224, 8: 256}
_TS_MAP = {5: 20, 6: 24, 7: 28, 8: 32, 9: 40}
_NMAS_NAMES = {0: "reserved", 1: "test", 2: "operational", 3: "dont_use"}

# Standard CRC-16 XMODEM lookup table used by Septentrio SBF block headers
def _crc16_xmodem(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def gst_to_utc(gst_wn: int, tow_sec: int) -> datetime:
    """Convert Galileo System Time (WN, TOW) to UTC (accounting for 1024-week offset & leap seconds)."""
    gps_wn = gst_wn + 1024
    return _GPS_EPOCH + timedelta(weeks=gps_wn, seconds=tow_sec - _GPS_UTC_LEAP_SECONDS)


@dataclass(frozen=True)
class OsnmaVerificationReport:
    """Detailed outcome of local Galileo OSNMA SIS ICD v1.1 verification."""

    outcome: str  # authenticated | failed | pending | unavailable
    authentication: str  # verified | failed | unknown
    merkle_proof_verified: bool
    ecdsa_kroot_verified: bool
    merkle_root_hex: str
    merkle_tree_uid: str | None
    public_key_uid: str | None
    pkid: int | None
    pk_type: str | None
    nma_status: str | None
    chain_id: int | None
    key_size_bits: int | None
    tag_size_bits: int | None
    mac_lookup_table: int | None
    gst_week: int | None
    gst_tow_start: int | None
    gst_tow_end: int | None
    observed_at_utc: str | None
    receiver_model: str | None
    receiver_firmware: str | None
    total_complete_subframes: int
    unauthenticated_zero_nma_subframes: int
    tesla_verified_subframes: int
    tag0_verified_count: int
    tag0_failed_count: int
    tag0_checked_count: int
    authenticated_svids: list[int]
    failure_reasons: list[str]


def verify_merkle_tree_xml(merkle_xml_path: Path) -> dict[str, Any]:
    """Parse GSC OSNMA_MerkleTree.xml and cryptographically verify leaf-to-root SHA-256 proof."""
    root = ET.parse(merkle_xml_path).getroot()
    mt = root.find(".//MerkleTree")
    if mt is None:
        raise ValueError(f"No <MerkleTree> element in {merkle_xml_path}")

    uid = mt.findtext("UID")
    issue_date = root.findtext(".//issueDate")
    pk_el = mt.find("PublicKey")
    if pk_el is None:
        raise ValueError(f"No <PublicKey> inside <MerkleTree> in {merkle_xml_path}")

    pk_idx = int(pk_el.findtext("i") or "0")
    pkid = int(pk_el.findtext("PKID") or "0")
    pk_type = (pk_el.findtext("PKType") or "").strip()
    pk_point_hex = (pk_el.findtext("point") or "").strip()
    pk_point = bytes.fromhex(pk_point_hex)
    npkt = 1 if "P-256" in pk_type else 3

    nodes: dict[tuple[int, int], bytes] = {}
    for tn in mt.findall("TreeNode"):
        j = int(tn.findtext("j") or "0")
        i = int(tn.findtext("i") or "0")
        nodes[(j, i)] = bytes.fromhex((tn.findtext("x_ji") or "").strip())

    # Leaf m_0 = SHA-256((NPKT << 4 | PKID) || PK_point)
    cur = hashlib.sha256(bytes([(npkt << 4) | pkid]) + pk_point).digest()
    idx = pk_idx
    max_level = max(j for (j, _) in nodes)
    for level in range(max_level):
        sib = nodes.get((level, idx ^ 1))
        if sib is None:
            return {
                "verified": False,
                "uid": uid,
                "issue_date": issue_date,
                "pkid": pkid,
                "pk_type": pk_type,
                "pk_point": pk_point,
                "merkle_root_hex": nodes.get((max_level, 0), b"").hex(),
            }
        cur = hashlib.sha256((cur + sib) if (idx % 2 == 0) else (sib + cur)).digest()
        idx //= 2

    expected_root = nodes.get((max_level, 0), b"")
    return {
        "verified": hmac.compare_digest(cur, expected_root),
        "uid": uid,
        "issue_date": issue_date,
        "pkid": pkid,
        "pk_type": pk_type,
        "pk_point": pk_point,
        "merkle_root_hex": expected_root.hex(),
    }


def _parse_pubkey_uid(pubkey_xml_path: Path | None) -> str | None:
    if pubkey_xml_path is None or not pubkey_xml_path.exists():
        return None
    root = ET.parse(pubkey_xml_path).getroot()
    return root.findtext(".//PublicKey/UID")


def verify_sbf_bytes(
    sbf_bytes: bytes,
    merkle_xml_path: Path = DEFAULT_MERKLE_PATH,
    pubkey_xml_path: Path | None = DEFAULT_PUBKEY_PATH,
    max_subframes: int | None = None,
) -> OsnmaVerificationReport:
    """Run local 4-layer Galileo OSNMA SIS ICD v1.1 verification over Septentrio SBF bytes."""
    try:
        import ecdsa
    except ImportError as exc:
        raise RuntimeError(
            "Optional Galileo OSNMA dependency 'ecdsa' is not installed. "
            "Install with: pip install -e '.[osnma]'"
        ) from exc

    mt_info = verify_merkle_tree_xml(merkle_xml_path)
    pubk_uid = _parse_pubkey_uid(pubkey_xml_path)
    failure_reasons: list[str] = []

    if not mt_info["verified"]:
        failure_reasons.append("MERKLE_PROOF_FAILED")

    vk = ecdsa.VerifyingKey.from_string(
        mt_info["pk_point"],
        curve=ecdsa.NIST256p,
        hashfunc=hashlib.sha256,
    )

    # Parse Septentrio SBF blocks (verifying CRC-16 XMODEM on each block)
    pos = 0
    subframes: dict[tuple[int, int, int], dict[int, tuple[int, str, int, int]]] = defaultdict(dict)
    receiver_model: str | None = None
    receiver_firmware: str | None = None
    n_bytes = len(sbf_bytes)

    while pos + 8 <= n_bytes:
        if sbf_bytes[pos : pos + 2] != b"$@":
            pos += 1
            continue
        crc_obs, bid_rev, length = struct.unpack_from("<HHH", sbf_bytes, pos + 2)
        if length < 8 or length % 4 != 0 or pos + length > n_bytes:
            pos += 1
            continue
        if _crc16_xmodem(sbf_bytes[pos + 4 : pos + length]) != crc_obs:
            pos += 1
            continue

        bid = bid_rev & 0x1FFF
        if bid == 5902 and receiver_model is None:
            raw_ascii = "".join(
                chr(b) if 32 <= b < 127 else "|" for b in sbf_bytes[pos + 14 : pos + length]
            )
            tokens = [t.strip() for t in raw_ascii.split("|") if len(t.strip()) >= 3]
            for tok in tokens:
                if "mosaic" in tok.lower() or "pola" in tok.lower() or "asterx" in tok.lower():
                    receiver_model = f"Septentrio {tok}"
                elif tok[0].isdigit() and "." in tok and receiver_firmware is None:
                    receiver_firmware = tok
        elif bid == 4023 and length >= 52:
            tow_ms, wnc, svid_raw, crc_ok, _vit, src, _freq, _rxch = struct.unpack_from(
                "<IHBBBBBB", sbf_bytes, pos + 8
            )
            if crc_ok == 1 and (src & 0x1F) == 17 and 71 <= svid_raw <= 106:
                tow = tow_ms // 1000
                shifted = tow - 3
                if shifted >= 0:
                    sf_tow = (shifted // 30) * 30
                    pidx = (shifted % 30) // 2
                    words = struct.unpack_from("<8I", sbf_bytes, pos + 20)
                    bitstr = "".join(f"{b:08b}" for b in struct.pack(">8I", *words))
                    word128 = bitstr[2:114] + bitstr[116:132]
                    wtype = int(word128[:6], 2)
                    hk = int(bitstr[132:140], 2)
                    mk = int(bitstr[140:172], 2)
                    subframes[(wnc - 1024, sf_tow, svid_raw - 70)][pidx] = (
                        wtype,
                        word128,
                        hk,
                        mk,
                    )
        pos += length

    # Collect complete 15-page (30-second) subframes
    complete_sfs: dict[tuple[int, int, int], tuple[dict[int, tuple[int, str, int, int]], bytes, bytes]] = {}
    kroot_blocks: dict[tuple[int, int], bytes] = {}
    nma_hdrs: dict[int, int] = {}
    zero_nma_count = 0

    for key in sorted(subframes.keys()):
        pmap = subframes[key]
        if len(pmap) != 15:
            continue
        if max_subframes is not None and len(complete_sfs) >= max_subframes:
            break
        hk = bytes(pmap[i][2] for i in range(15))
        mk = b"".join(struct.pack(">I", pmap[i][3]) for i in range(15))
        complete_sfs[key] = (pmap, hk, mk)
        if hk[0] == 0:
            zero_nma_count += 1
            continue
        dsm_id = (hk[1] >> 4) & 0xF
        dsm_bid = hk[1] & 0xF
        if dsm_id < 12:
            kroot_blocks[(dsm_id, dsm_bid)] = hk[2:]
            nma_hdrs[dsm_id] = hk[0]

    if not complete_sfs:
        return OsnmaVerificationReport(
            outcome="unavailable",
            authentication="unknown",
            merkle_proof_verified=mt_info["verified"],
            ecdsa_kroot_verified=False,
            merkle_root_hex=mt_info["merkle_root_hex"],
            merkle_tree_uid=mt_info["uid"],
            public_key_uid=pubk_uid,
            pkid=mt_info["pkid"],
            pk_type=mt_info["pk_type"],
            nma_status=None,
            chain_id=None,
            key_size_bits=None,
            tag_size_bits=None,
            mac_lookup_table=None,
            gst_week=None,
            gst_tow_start=None,
            gst_tow_end=None,
            observed_at_utc=None,
            receiver_model=receiver_model,
            receiver_firmware=receiver_firmware,
            total_complete_subframes=0,
            unauthenticated_zero_nma_subframes=0,
            tesla_verified_subframes=0,
            tag0_verified_count=0,
            tag0_failed_count=0,
            tag0_checked_count=0,
            authenticated_svids=[],
            failure_reasons=failure_reasons,
        )

    all_wns = [k[0] for k in complete_sfs]
    all_tows = [k[1] for k in complete_sfs]
    gst_week = all_wns[0]
    gst_tow_start = min(all_tows)
    gst_tow_end = max(all_tows)
    observed_at_utc = gst_to_utc(gst_week, gst_tow_start).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not kroot_blocks:
        return OsnmaVerificationReport(
            outcome="unavailable",
            authentication="unknown",
            merkle_proof_verified=mt_info["verified"],
            ecdsa_kroot_verified=False,
            merkle_root_hex=mt_info["merkle_root_hex"],
            merkle_tree_uid=mt_info["uid"],
            public_key_uid=pubk_uid,
            pkid=mt_info["pkid"],
            pk_type=mt_info["pk_type"],
            nma_status=None,
            chain_id=None,
            key_size_bits=None,
            tag_size_bits=None,
            mac_lookup_table=None,
            gst_week=gst_week,
            gst_tow_start=gst_tow_start,
            gst_tow_end=gst_tow_end,
            observed_at_utc=observed_at_utc,
            receiver_model=receiver_model,
            receiver_firmware=receiver_firmware,
            total_complete_subframes=len(complete_sfs),
            unauthenticated_zero_nma_subframes=zero_nma_count,
            tesla_verified_subframes=0,
            tag0_verified_count=0,
            tag0_failed_count=0,
            tag0_checked_count=0,
            authenticated_svids=[],
            failure_reasons=failure_reasons,
        )

    # Assemble & verify DSM-KROOT
    ecdsa_verified = False
    kroot_params: dict[str, Any] = {}
    for dsm_id in sorted(set(k[0] for k in kroot_blocks)):
        if (dsm_id, 0) not in kroot_blocks:
            continue
        nb_dk = (kroot_blocks[(dsm_id, 0)][0] >> 4) & 0xF
        nb = _NB_DK_MAP.get(nb_dk, 0)
        if nb == 0 or not all((dsm_id, i) in kroot_blocks for i in range(nb)):
            continue
        dsm = b"".join(kroot_blocks[(dsm_id, i)] for i in range(nb))
        dsm_bits = "".join(f"{x:08b}" for x in dsm)
        pkid = int(dsm_bits[4:8], 2)
        cidkr = int(dsm_bits[8:10], 2)
        ks = _KS_MAP.get(int(dsm_bits[16:20], 2))
        ts = _TS_MAP.get(int(dsm_bits[20:24], 2))
        maclt = int(dsm_bits[24:32], 2)
        wn_k = int(dsm_bits[36:48], 2)
        towh_k = int(dsm_bits[48:56], 2)
        if ks is None or ts is None:
            continue
        alpha_bytes = int(dsm_bits[56:104], 2).to_bytes(6, "big")
        kroot_bytes = int(dsm_bits[104 : 104 + ks], 2).to_bytes(ks // 8, "big")
        ds_bits = dsm_bits[104 + ks : 104 + ks + 512]
        nma_hdr = nma_hdrs[dsm_id]
        nmas_val = (nma_hdr >> 6) & 0x3

        msg_bits = f"{nma_hdr:08b}" + dsm_bits[8 : 104 + ks]
        msg_bytes = int(msg_bits, 2).to_bytes(len(msg_bits) // 8, "big")
        sig_bytes = int(ds_bits, 2).to_bytes(64, "big")

        kroot_params = {
            "pkid": pkid,
            "cidkr": cidkr,
            "ks": ks,
            "ts": ts,
            "maclt": maclt,
            "wn_k": wn_k,
            "towh_k": towh_k,
            "alpha_bytes": alpha_bytes,
            "kroot_bytes": kroot_bytes,
            "nma_status": _NMAS_NAMES.get(nmas_val, "unknown"),
        }
        try:
            ecdsa_verified = bool(
                vk.verify(
                    sig_bytes,
                    msg_bytes,
                    hashfunc=hashlib.sha256,
                    sigdecode=ecdsa.util.sigdecode_string,
                )
            )
        except Exception:
            ecdsa_verified = False
            failure_reasons.append("DSM_KROOT_SIGNATURE_FAILED")
        break

    if not kroot_params:
        # DSM-KROOT still incomplete across available subframes -> pending
        return OsnmaVerificationReport(
            outcome="pending",
            authentication="unknown",
            merkle_proof_verified=mt_info["verified"],
            ecdsa_kroot_verified=False,
            merkle_root_hex=mt_info["merkle_root_hex"],
            merkle_tree_uid=mt_info["uid"],
            public_key_uid=pubk_uid,
            pkid=mt_info["pkid"],
            pk_type=mt_info["pk_type"],
            nma_status=None,
            chain_id=None,
            key_size_bits=None,
            tag_size_bits=None,
            mac_lookup_table=None,
            gst_week=gst_week,
            gst_tow_start=gst_tow_start,
            gst_tow_end=gst_tow_end,
            observed_at_utc=observed_at_utc,
            receiver_model=receiver_model,
            receiver_firmware=receiver_firmware,
            total_complete_subframes=len(complete_sfs),
            unauthenticated_zero_nma_subframes=zero_nma_count,
            tesla_verified_subframes=0,
            tag0_verified_count=0,
            tag0_failed_count=0,
            tag0_checked_count=0,
            authenticated_svids=[],
            failure_reasons=failure_reasons,
        )

    if not mt_info["verified"] or not ecdsa_verified:
        return OsnmaVerificationReport(
            outcome="failed",
            authentication="failed",
            merkle_proof_verified=mt_info["verified"],
            ecdsa_kroot_verified=ecdsa_verified,
            merkle_root_hex=mt_info["merkle_root_hex"],
            merkle_tree_uid=mt_info["uid"],
            public_key_uid=pubk_uid,
            pkid=kroot_params["pkid"],
            pk_type=mt_info["pk_type"],
            nma_status=kroot_params["nma_status"],
            chain_id=kroot_params["cidkr"],
            key_size_bits=kroot_params["ks"],
            tag_size_bits=kroot_params["ts"],
            mac_lookup_table=kroot_params["maclt"],
            gst_week=gst_week,
            gst_tow_start=gst_tow_start,
            gst_tow_end=gst_tow_end,
            observed_at_utc=observed_at_utc,
            receiver_model=receiver_model,
            receiver_firmware=receiver_firmware,
            total_complete_subframes=len(complete_sfs),
            unauthenticated_zero_nma_subframes=zero_nma_count,
            tesla_verified_subframes=0,
            tag0_verified_count=0,
            tag0_failed_count=0,
            tag0_checked_count=0,
            authenticated_svids=[],
            failure_reasons=failure_reasons,
        )

    # Layer 3: Verify TESLA one-way SHA-256 key chain back to KROOT
    ks = kroot_params["ks"]
    ts = kroot_params["ts"]
    ks_bytes = ks // 8
    num_tags = (480 - ks) // (ts + 16)
    key_bit_start = (ts + 16) * num_tags
    key_byte_start = key_bit_start // 8

    kroot_gst = kroot_params["wn_k"] * 604800 + kroot_params["towh_k"] * 3600
    alpha_bytes = kroot_params["alpha_bytes"]
    kroot_bytes = kroot_params["kroot_bytes"]
    verified_keys: dict[tuple[int, int], bytes] = {}

    for (wn, sf_tow, _svid), (_pmap, hk, mk) in complete_sfs.items():
        if hk[0] == 0:
            continue
        key_bytes = mk[key_byte_start : key_byte_start + ks_bytes]
        sf_gst = wn * 604800 + sf_tow
        steps = (sf_gst - kroot_gst) // 30 + 1
        if 1 <= steps <= 500:
            cur = key_bytes
            cur_gst = sf_gst - 30
            for _ in range(steps):
                gst_u32 = (
                    (((cur_gst // 604800) & 0xFFF) << 20)
                    | ((cur_gst % 604800) & 0xFFFFF)
                )
                cur = hashlib.sha256(
                    cur + struct.pack(">I", gst_u32) + alpha_bytes
                ).digest()[:ks_bytes]
                cur_gst -= 30
            if hmac.compare_digest(cur, kroot_bytes):
                verified_keys[(wn, sf_tow - 30)] = key_bytes

    # Layer 4: Verify real Galileo I/NAV ADKD=0 (WT1-5 ephemeris+clock) HMAC-SHA-256 Tag0
    tag0_verified = 0
    tag0_failed = 0
    tag0_checked = 0
    verified_svids: set[int] = set()
    first_verified_sf: tuple[int, int] | None = None

    for (wn, sf_tow, svid), (_pmap, hk, mk) in sorted(complete_sfs.items()):
        if (wn, sf_tow) not in verified_keys or hk[0] == 0:
            continue
        prev_key = (wn, sf_tow - 30, svid)
        if prev_key not in complete_sfs:
            continue
        by_wt = {wt: w128 for (wt, w128, _, _) in complete_sfs[prev_key][0].values()}
        if not all(w in by_wt for w in (1, 2, 3, 4, 5)):
            continue
        nav_bits = (
            by_wt[1][6:126]
            + by_wt[2][6:126]
            + by_wt[3][6:128]
            + by_wt[4][6:126]
            + by_wt[5][6:73]
        )
        mk_bits = "".join(f"{b:08b}" for b in mk)
        tag0_bits = mk_bits[:ts]
        nmas = (hk[0] >> 6) & 0x3
        mac_bits = f"{svid:08b}{wn:012b}{sf_tow:020b}{1:08b}{nmas:02b}" + nav_bits
        pad = (8 - (len(mac_bits) % 8)) % 8
        mac_in = int(mac_bits + ("0" * pad), 2).to_bytes((len(mac_bits) + pad) // 8, "big")
        digest = hmac.new(verified_keys[(wn, sf_tow)], mac_in, hashlib.sha256).digest()
        computed_bits = "".join(f"{b:08b}" for b in digest)[:ts]

        tag0_checked += 1
        if hmac.compare_digest(computed_bits, tag0_bits):
            tag0_verified += 1
            verified_svids.add(svid)
            if first_verified_sf is None:
                first_verified_sf = (wn, sf_tow)
        else:
            tag0_failed += 1
            if "MAC_TAG_VERIFICATION_FAILED" not in failure_reasons:
                failure_reasons.append("MAC_TAG_VERIFICATION_FAILED")

    if first_verified_sf is not None:
        observed_at_utc = gst_to_utc(*first_verified_sf).strftime("%Y-%m-%dT%H:%M:%SZ")

    if tag0_failed > 0:
        outcome = "failed"
        auth = "failed"
    elif tag0_verified > 0:
        outcome = "authenticated"
        auth = "verified"
    else:
        outcome = "pending"
        auth = "unknown"

    return OsnmaVerificationReport(
        outcome=outcome,
        authentication=auth,
        merkle_proof_verified=mt_info["verified"],
        ecdsa_kroot_verified=ecdsa_verified,
        merkle_root_hex=mt_info["merkle_root_hex"],
        merkle_tree_uid=mt_info["uid"],
        public_key_uid=pubk_uid,
        pkid=kroot_params["pkid"],
        pk_type=mt_info["pk_type"],
        nma_status=kroot_params["nma_status"],
        chain_id=kroot_params["cidkr"],
        key_size_bits=ks,
        tag_size_bits=ts,
        mac_lookup_table=kroot_params["maclt"],
        gst_week=gst_week,
        gst_tow_start=gst_tow_start,
        gst_tow_end=gst_tow_end,
        observed_at_utc=observed_at_utc,
        receiver_model=receiver_model,
        receiver_firmware=receiver_firmware,
        total_complete_subframes=len(complete_sfs),
        unauthenticated_zero_nma_subframes=zero_nma_count,
        tesla_verified_subframes=len(verified_keys),
        tag0_verified_count=tag0_verified,
        tag0_failed_count=tag0_failed,
        tag0_checked_count=tag0_checked,
        authenticated_svids=sorted(verified_svids),
        failure_reasons=failure_reasons,
    )


def extract_galileo_osnma_evidence(
    sbf_path: Path = DEFAULT_SBF_PATH,
    merkle_xml_path: Path = DEFAULT_MERKLE_PATH,
    pubkey_xml_path: Path = DEFAULT_PUBKEY_PATH,
    source_url: str = DEFAULT_SBF_SOURCE_URL,
    retrieved_at: str = "2026-11-27T16:58:00Z",
) -> dict[str, Any]:
    """Verify a local recorded Galileo SBF archive and return a validated Evidence dict."""
    resolved_sbf = sbf_path.resolve()
    sbf_bytes = resolved_sbf.read_bytes()
    sbf_sha256 = compute_file_sha256(resolved_sbf)
    merkle_sha256 = compute_file_sha256(merkle_xml_path.resolve())
    pubkey_sha256 = compute_file_sha256(pubkey_xml_path.resolve())
    rel_raw_path = resolved_sbf.relative_to(REPO_ROOT).as_posix()

    report = verify_sbf_bytes(
        sbf_bytes=sbf_bytes,
        merkle_xml_path=merkle_xml_path,
        pubkey_xml_path=pubkey_xml_path,
    )

    svid_list_str = ", ".join(f"E{s:02d}" for s in report.authenticated_svids) or "none"
    limitations = [
        "Galileo OSNMA cryptographically authenticates broadcast I/NAV navigation message data bits (ADKD=0: ephemeris, clock, ionospheric/BGD, health/DVS) ONLY — it does NOT authenticate user position accuracy, pseudorange measurements, receiver integrity, or protect against replay/meaconing spoofing.",
        "Recorded receiver data verification does not perform live Galileo System Time (GST) loose time synchronisation checks required for real-time TESLA security against delayed replay.",
    ]
    if report.nma_status == "test":
        limitations.append(
            "Broadcast NMA Header status is NMAS=1 ('test', Galileo OSNMA public test phase, August 2023), not operational service (NMAS=2)."
        )
    if report.unauthenticated_zero_nma_subframes > 0:
        limitations.append(
            f"{report.unauthenticated_zero_nma_subframes} complete subframes in the recording had NMA_Header=0x00 (OSNMA not broadcast on that satellite/subframe)."
        )
    limitations.append(
        "Recording publication/availability timestamp (available_at) is not embedded in the SBF file and remains unknown (null)."
    )

    evidence_dict: dict[str, Any] = {
        "id": f"galileo-osnma-sbf-wn{report.gst_week or 0}-pkid{report.pkid or 0}",
        "source": "galileo_osnma_sbf",
        "product_id": f"OSNMA_SBF_WN{report.gst_week or 0}_PKID{report.pkid or 0}",
        "source_url": source_url,
        "observed_at": report.observed_at_utc,
        "available_at": None,
        "retrieved_at": retrieved_at,
        "kind": "gnss_osnma_auth",
        "geometry": None,
        "coverage": None,
        "attributes": {
            "verification_method": "local_osnma_cryptographic",
            "locally_verified": True,
            "osnma_outcome": report.outcome,
            "authenticated_scope": (
                "Galileo E1-B I/NAV ADKD=0 navigation data (Word Types 1-5: ephemeris, "
                "clock corrections, ionospheric/BGD, health/DVS)"
            ),
            "does_not_authenticate": [
                "user_position_accuracy",
                "pseudorange_integrity",
                "receiver_firmware_trustworthiness",
                "protection_against_meaconing_or_relay_spoofing",
            ],
            "merkle_proof_verified": report.merkle_proof_verified,
            "ecdsa_kroot_verified": report.ecdsa_kroot_verified,
            "merkle_root_sha256": report.merkle_root_hex,
            "merkle_tree_uid": report.merkle_tree_uid,
            "public_key_uid": report.public_key_uid,
            "pkid": report.pkid,
            "pk_type": report.pk_type,
            "nma_status": report.nma_status,
            "chain_id": report.chain_id,
            "key_size_bits": report.key_size_bits,
            "tag_size_bits": report.tag_size_bits,
            "mac_lookup_table": report.mac_lookup_table,
            "gst_week": report.gst_week,
            "gst_tow_start": report.gst_tow_start,
            "gst_tow_end": report.gst_tow_end,
            "receiver_model": report.receiver_model,
            "receiver_firmware": report.receiver_firmware,
            "total_complete_subframes": report.total_complete_subframes,
            "unauthenticated_zero_nma_subframes": report.unauthenticated_zero_nma_subframes,
            "tesla_verified_subframes": report.tesla_verified_subframes,
            "tag0_verified_count": report.tag0_verified_count,
            "tag0_failed_count": report.tag0_failed_count,
            "tag0_checked_count": report.tag0_checked_count,
            "authenticated_svids": report.authenticated_svids,
            "failure_reasons": report.failure_reasons,
            "merkle_tree_sha256": merkle_sha256,
            "public_key_sha256": pubkey_sha256,
        },
        "provenance": {
            "original_source": (
                f"Galileo E1-B Signal-in-Space ({svid_list_str}) recorded via "
                f"{report.receiver_model or 'Septentrio SBF receiver'}"
            ),
            "publishing_organisation": (
                "European GNSS Service Centre (GSC cryptographic material) & "
                "Algafix/OSNMA KU Leuven (recorded SBF)"
            ),
            "upstream_datasets": [
                x for x in (report.merkle_tree_uid, report.public_key_uid) if x
            ],
            "derived_from": [],
            "measurement_method": (
                "Local Galileo OSNMA SIS ICD v1.1 verification "
                "(Merkle SHA-256 + ECDSA P-256 DSM-KROOT + TESLA SHA-256 + HMAC-SHA-256 ADKD=0)"
            ),
            "shared_dependencies": ["galileo_system_time_gst"],
        },
        "authentication": report.authentication,
        "sha256": sbf_sha256,
        "raw_path": rel_raw_path,
        "licence": (
            "EUPL-1.2 (recorded SBF from Algafix/OSNMA, KU Leuven) & "
            "European GNSS Service Centre (GSC) public OSNMA cryptographic material (© European Union)"
        ),
        "limitations": limitations,
        "synthetic": False,
    }

    validated = Evidence.model_validate(evidence_dict)
    return validated.model_dump(mode="json")


class GalileoOsnmaConnector:
    """EvidenceConnector implementation performing local Galileo OSNMA verification."""

    def __init__(
        self,
        sbf_path: Path = DEFAULT_SBF_PATH,
        merkle_xml_path: Path = DEFAULT_MERKLE_PATH,
        pubkey_xml_path: Path = DEFAULT_PUBKEY_PATH,
        source_url: str = DEFAULT_SBF_SOURCE_URL,
        retrieved_at: str = "2026-11-27T16:58:00Z",
    ) -> None:
        self._sbf_path = sbf_path
        self._merkle_xml_path = merkle_xml_path
        self._pubkey_xml_path = pubkey_xml_path
        self._source_url = source_url
        self._retrieved_at = retrieved_at
        self._metadata = ConnectorMetadata(
            connector_id="galileo-osnma",
            source_name="galileo_osnma_sbf",
            publishing_organisation="European GNSS Service Centre (GSC) & Algafix/OSNMA",
            produced_evidence_kinds=["gnss_osnma_auth"],
            supports_authentication=True,
            notes=[
                "Performs local 4-layer Galileo OSNMA SIS ICD v1.1 cryptographic verification offline.",
                "Authenticates broadcast I/NAV ADKD=0 navigation data bits only (not user positioning accuracy).",
            ],
        )

    @property
    def metadata(self) -> ConnectorMetadata:
        return self._metadata

    def load_evidence(self) -> list[Evidence]:
        raw = extract_galileo_osnma_evidence(
            sbf_path=self._sbf_path,
            merkle_xml_path=self._merkle_xml_path,
            pubkey_xml_path=self._pubkey_xml_path,
            source_url=self._source_url,
            retrieved_at=self._retrieved_at,
        )
        return [Evidence.model_validate(raw)]


def create_tampered_sbf_copy(sbf_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    """Create a controlled in-memory tampered copy of recorded SBF bytes.

    Flips 1 bit inside a genuine Galileo Word Type 1 (ephemeris) navigation
    payload and recomputes the Septentrio SBF block CRC-16 XMODEM so packet
    framing remains valid — demonstrating that OSNMA HMAC-SHA-256 catches
    navigation-message tampering that transport CRCs cannot detect.
    """
    raw = bytearray(sbf_bytes)
    pos = 0
    seen = 0
    while pos + 8 <= len(raw):
        if raw[pos : pos + 2] != b"$@":
            pos += 1
            continue
        _crc_obs, bid_rev, length = struct.unpack_from("<HHH", raw, pos + 2)
        if length < 8 or length % 4 != 0 or pos + length > len(raw):
            pos += 1
            continue
        if (bid_rev & 0x1FFF) == 4023 and length >= 52:
            seen += 1
            if seen > 400:
                tow_ms, wnc, svid_raw, crc_ok, _vit, src = struct.unpack_from(
                    "<IHBBBB", raw, pos + 8
                )
                words = struct.unpack_from("<8I", raw, pos + 20)
                wtype = (words[0] >> 24) & 0x3F
                if crc_ok == 1 and (src & 0x1F) == 17 and wtype == 1:
                    orig_w1 = words[1]
                    tampered_w1 = orig_w1 ^ 0x00000400
                    struct.pack_into("<I", raw, pos + 24, tampered_w1)
                    new_crc = _crc16_xmodem(bytes(raw[pos + 4 : pos + length]))
                    struct.pack_into("<H", raw, pos + 2, new_crc)
                    return bytes(raw), {
                        "svid": svid_raw - 70,
                        "svid_label": f"E{svid_raw - 70:02d}",
                        "gst_week": wnc - 1024,
                        "gst_tow": tow_ms // 1000,
                        "word_type": 1,
                        "word_description": "Galileo I/NAV Word Type 1 (Ephemeris: t0e, M0, e, sqrt(A))",
                        "bit_mask": "0x00000400",
                        "original_word_hex": f"0x{orig_w1:08x}",
                        "tampered_word_hex": f"0x{tampered_w1:08x}",
                        "sbf_block_crc_recomputed": True,
                        "note": (
                            "1 single bit flipped in Word Type 1 ephemeris payload; Septentrio SBF "
                            "CRC-16 was recomputed so receiver framing still accepts the packet, "
                            "leaving only OSNMA HMAC-SHA-256 to detect the modification."
                        ),
                    }
        pos += length
    raise ValueError("Could not locate a suitable Galileo Word Type 1 block to tamper.")


def build_tampered_galileo_evidence(
    sbf_path: Path = DEFAULT_SBF_PATH,
    merkle_xml_path: Path = DEFAULT_MERKLE_PATH,
    pubkey_xml_path: Path = DEFAULT_PUBKEY_PATH,
) -> tuple[Evidence, dict[str, Any]]:
    """Run real local OSNMA verification on a deliberately tampered copy of the SBF recording."""
    orig_bytes = sbf_path.resolve().read_bytes()
    tampered_bytes, tamper_details = create_tampered_sbf_copy(orig_bytes)
    tampered_sha = hashlib.sha256(tampered_bytes).hexdigest()
    merkle_sha = compute_file_sha256(merkle_xml_path.resolve())
    pubkey_sha = compute_file_sha256(pubkey_xml_path.resolve())

    report = verify_sbf_bytes(
        sbf_bytes=tampered_bytes,
        merkle_xml_path=merkle_xml_path,
        pubkey_xml_path=pubkey_xml_path,
    )

    ev = Evidence.model_validate(
        {
            "id": "synthetic-galileo-osnma-tampered-1bit",
            "source": "galileo_osnma_tamper_test",
            "product_id": f"TAMPERED_COPY_OSNMA_WN{report.gst_week or 0}_PKID{report.pkid or 0}",
            "source_url": None,
            "observed_at": report.observed_at_utc,
            "available_at": None,
            "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kind": "gnss_osnma_auth",
            "geometry": None,
            "coverage": None,
            "attributes": {
                "verification_method": "local_osnma_cryptographic",
                "locally_verified": True,
                "osnma_outcome": report.outcome,
                "authenticated_scope": (
                    "Controlled offline tamper test copy (1 bit flipped in Galileo I/NAV Word Type 1 ephemeris)"
                ),
                "merkle_proof_verified": report.merkle_proof_verified,
                "ecdsa_kroot_verified": report.ecdsa_kroot_verified,
                "merkle_root_sha256": report.merkle_root_hex,
                "merkle_tree_uid": report.merkle_tree_uid,
                "public_key_uid": report.public_key_uid,
                "pkid": report.pkid,
                "pk_type": report.pk_type,
                "nma_status": report.nma_status,
                "chain_id": report.chain_id,
                "key_size_bits": report.key_size_bits,
                "tag_size_bits": report.tag_size_bits,
                "mac_lookup_table": report.mac_lookup_table,
                "gst_week": report.gst_week,
                "gst_tow_start": report.gst_tow_start,
                "gst_tow_end": report.gst_tow_end,
                "receiver_model": report.receiver_model,
                "receiver_firmware": report.receiver_firmware,
                "total_complete_subframes": report.total_complete_subframes,
                "unauthenticated_zero_nma_subframes": report.unauthenticated_zero_nma_subframes,
                "tesla_verified_subframes": report.tesla_verified_subframes,
                "tag0_verified_count": report.tag0_verified_count,
                "tag0_failed_count": report.tag0_failed_count,
                "tag0_checked_count": report.tag0_checked_count,
                "authenticated_svids": report.authenticated_svids,
                "failure_reasons": report.failure_reasons,
                "merkle_tree_sha256": merkle_sha,
                "public_key_sha256": pubkey_sha,
                "tamper_details": tamper_details,
            },
            "provenance": {
                "original_source": (
                    f"Deliberately modified copy of {report.receiver_model or 'Septentrio'} SBF recording"
                ),
                "publishing_organisation": "EIP Local Offline Tamper Demonstration (Synthetic Test)",
                "upstream_datasets": [
                    x for x in (report.merkle_tree_uid, report.public_key_uid) if x
                ],
                "derived_from": [f"galileo-osnma-sbf-wn{report.gst_week or 0}-pkid{report.pkid or 0}"],
                "measurement_method": "Local Galileo OSNMA SIS ICD v1.1 verification on 1-bit tampered SBF copy",
                "shared_dependencies": ["galileo_system_time_gst"],
            },
            "authentication": report.authentication,
            "sha256": tampered_sha,
            "raw_path": None,
            "licence": "Synthetic deliberately tampered test copy (derived locally in memory from EUPL-1.2 recording)",
            "limitations": [
                "DELIBERATELY TAMPERED SYNTHETIC TEST EVIDENCE: 1 bit was flipped in a copy of the recorded Galileo Word Type 1 ephemeris to demonstrate cryptographic failure detection.",
                "Merkle proof, ECDSA signature, and TESLA key chain still verify against the unmodified key stream, while Stage 4 HMAC-SHA-256 Tag0 verification fails on the modified subframe.",
            ],
            "synthetic": True,
        }
    )
    return ev, tamper_details
