import type { Evidence, GalileoTamperComparison } from "../types/contract";

interface GalileoPanelProps {
  evidence: Evidence | null;
  tamperComparison: GalileoTamperComparison | null;
  tamperLoading: boolean;
  tamperError: string | null;
  mockMode: boolean;
  onRunTamperDemo: () => void;
  onClearTamperDemo: () => void;
}

function StageRow({
  num,
  title,
  passed,
  detail,
  extra,
}: {
  num: number;
  title: string;
  passed: boolean;
  detail: string;
  extra?: string;
}) {
  return (
    <div className={`crypto-step ${passed ? "crypto-step-ok" : "crypto-step-fail"}`}>
      <span className={`step-num ${passed ? "" : "step-num-fail"}`}>{num}</span>
      <div>
        <div className="finding-header">
          <strong>{title}</strong>
          <span className={`mini-badge ${passed ? "mini-real" : "mini-danger"}`}>
            {passed ? "Verified locally" : "FAILED"}
          </span>
        </div>
        <p className="muted-note">{detail}</p>
        {extra && <code className="hash-code">{extra}</code>}
      </div>
    </div>
  );
}

export function GalileoPanel({
  evidence,
  tamperComparison,
  tamperLoading,
  tamperError,
  mockMode,
  onRunTamperDemo,
  onClearTamperDemo,
}: GalileoPanelProps) {
  const attrs = evidence?.attributes ?? {};
  const tagVerified = Number(attrs.tag0_verified_count ?? 0);
  const tagChecked = Number(attrs.tag0_checked_count ?? 0);
  const tagFailed = Number(attrs.tag0_failed_count ?? 0);

  return (
    <section
      className="panel crypto-panel"
      aria-label="Galileo OSNMA verification overview"
      data-testid="galileo-crypto-panel"
    >
      <div className="panel-header">
        <h2>Galileo OSNMA 4-Stage Cryptographic Verification</h2>
        <span className="panel-tag">SIS ICD v1.1 · Offline Local</span>
      </div>

      {!evidence ? (
        <div className="empty-state">
          No Galileo OSNMA evidence records loaded in active store.
        </div>
      ) : (
        <div className="crypto-stack">
          <div className="crypto-banner">
            <strong>What OSNMA Cryptographically Authenticates:</strong>{" "}
            {String(
              attrs.authenticated_scope ??
                "Galileo E1-B I/NAV ADKD=0 navigation data (Word Types 1-5: ephemeris, clock, iono/BGD, health/DVS)",
            )}
          </div>

          <div className="crypto-layers">
            <StageRow
              num={1}
              title="Merkle Tree Proof (SHA-256)"
              passed={Boolean(attrs.merkle_proof_verified)}
              detail={`PKID ${String(attrs.pkid ?? "?")} (${String(attrs.pk_type ?? "?")}) verified against official GSC Merkle Tree (${String(attrs.merkle_tree_uid ?? "N/A")})`}
              extra={`Merkle Root: ${String(attrs.merkle_root_sha256 ?? "N/A")}`}
            />
            <StageRow
              num={2}
              title="DSM-KROOT Digital Signature (ECDSA P-256)"
              passed={Boolean(attrs.ecdsa_kroot_verified)}
              detail={`ECDSA P-256/SHA-256 signature over NMA_Header || DSM-KROOT · Chain ID ${String(attrs.chain_id ?? "?")} · Broadcast NMAS: ${String(attrs.nma_status ?? "?")}`}
            />
            <StageRow
              num={3}
              title="TESLA One-Way Key Chain (SHA-256)"
              passed={Number(attrs.tesla_verified_subframes ?? 0) > 0}
              detail={`${String(attrs.tesla_verified_subframes ?? 0)} complete 30-second subframes cryptographically chained back to KROOT (Key size ${String(attrs.key_size_bits ?? "?")} bits)`}
            />
            <StageRow
              num={4}
              title="Navigation-Data MAC Verification (HMAC-SHA-256 ADKD=0)"
              passed={tagVerified > 0 && tagFailed === 0}
              detail={`Tags verified: ${tagVerified} / ${tagChecked} (${String(attrs.tag_size_bits ?? "?")}-bit tags, ${tagFailed} failed) · SVIDs: ${
                Array.isArray(attrs.authenticated_svids)
                  ? (attrs.authenticated_svids as number[])
                      .map((s) => `E${String(s).padStart(2, "0")}`)
                      .join(", ")
                  : "none"
              }`}
            />
          </div>

          {/* Controlled Offline Tampering Demonstration */}
          <div className="tamper-box" data-testid="galileo-tamper-section">
            <div className="finding-header">
              <strong>Controlled Offline Tampering Demonstration</strong>
              <div className="badge-row">
                <button
                  type="button"
                  className="btn-primary"
                  onClick={onRunTamperDemo}
                  disabled={tamperLoading || mockMode}
                  data-testid="run-tamper-demo-button"
                >
                  {tamperLoading
                    ? "Running local crypto verification…"
                    : "Compare Original vs. 1-Bit Tampered SBF"}
                </button>
                {tamperComparison && (
                  <button type="button" className="btn-ghost" onClick={onClearTamperDemo}>
                    Reset
                  </button>
                )}
              </div>
            </div>
            <p className="muted-note">
              Creates an in-memory copy of the genuine recorded SBF file, flips 1 single bit inside a
              Galileo Word Type 1 ephemeris word (recomputing the SBF transport CRC-16), and runs the
              real backend 4-layer OSNMA verifier on both files side-by-side.
            </p>

            {tamperError && (
              <div className="error-box" role="alert">
                {tamperError}
              </div>
            )}

            {tamperComparison && (
              <div className="tamper-comparison" data-testid="tamper-comparison-result">
                <div className="tamper-diff-banner">
                  <strong>Modified Bit Details (SYNTHETIC TAMPER TEST):</strong>{" "}
                  {tamperComparison.tamper_details.svid_label} · GST WN{" "}
                  {tamperComparison.tamper_details.gst_week} TOW{" "}
                  {tamperComparison.tamper_details.gst_tow} · Word Type{" "}
                  {tamperComparison.tamper_details.word_type} ·{" "}
                  <code>{tamperComparison.tamper_details.original_word_hex}</code> →{" "}
                  <code>{tamperComparison.tamper_details.tampered_word_hex}</code> (SBF CRC-16
                  recomputed)
                </div>

                <div className="tamper-grid">
                  <div className="tamper-card tamper-card-orig">
                    <div className="finding-header">
                      <strong>Original Recorded SBF</strong>
                      <span className="mini-badge mini-real">Genuine (synthetic: false)</span>
                    </div>
                    <p>
                      Outcome: <code>{tamperComparison.original.assessment.status}</code>
                    </p>
                    <p className="muted-note">
                      Stage 1 Merkle: ✓ · Stage 2 ECDSA: ✓ · Stage 3 TESLA:{" "}
                      {String(
                        tamperComparison.original.evidence[0]?.attributes?.tesla_verified_subframes,
                      )}{" "}
                      · Stage 4 MAC:{" "}
                      <strong>
                        {String(
                          tamperComparison.original.evidence[0]?.attributes?.tag0_verified_count,
                        )}{" "}
                        /{" "}
                        {String(
                          tamperComparison.original.evidence[0]?.attributes?.tag0_checked_count,
                        )}{" "}
                        verified
                      </strong>
                    </p>
                  </div>

                  <div className="tamper-card tamper-card-mod">
                    <div className="finding-header">
                      <strong>1-Bit Tampered Copy</strong>
                      <span className="mini-badge mini-danger">Synthetic Tampered Test</span>
                    </div>
                    <p>
                      Outcome: <code>{tamperComparison.tampered.assessment.status}</code> (
                      <code>{tamperComparison.tampered.assessment.reasons.join(", ")}</code>)
                    </p>
                    <p className="muted-note">
                      Stage 1 Merkle: ✓ · Stage 2 ECDSA: ✓ · Stage 3 TESLA:{" "}
                      {String(
                        tamperComparison.tampered.evidence[0]?.attributes?.tesla_verified_subframes,
                      )}{" "}
                      · Stage 4 MAC:{" "}
                      <strong>
                        {String(
                          tamperComparison.tampered.evidence[0]?.attributes?.tag0_failed_count,
                        )}{" "}
                        FAILED (HMAC mismatch detected)
                      </strong>
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Explicit 5-Point Scope & Trust Disclosures */}
          <div className="scope-warning-box" data-testid="galileo-scope-disclosures">
            <strong>Explicit Verification Scope &amp; Limitations:</strong>
            <ul>
              <li>
                <strong>2023 Public Test Phase:</strong> Recording originates from the August 2023
                Galileo OSNMA public test phase (<code>NMAS=1 [test]</code>), not operational
                service (<code>NMAS=2</code>).
              </li>
              <li>
                <strong>Retrospective &amp; Offline:</strong> Cryptographic verification is performed
                offline over recorded Septentrio <code>mosaic-X5</code> SBF data.
              </li>
              <li>
                <strong>Not Positioning Accuracy:</strong> Authenticated navigation messages do NOT
                establish accurate user positioning, valid pseudoranges, or trustworthy receiver
                behaviour.
              </li>
              <li>
                <strong>No Real-Time Replay Protection:</strong> Live Galileo System Time (GST)
                loose synchronisation and meaconing/replay defense have not been demonstrated.
              </li>
              <li>
                <strong>Trust Anchor Dependency:</strong> Verification depends on trusted official
                GSC public-key and Merkle-root cryptographic material.
              </li>
            </ul>
          </div>

          <dl className="meta-grid">
            <div>
              <dt>Verification Method</dt>
              <dd>
                <code>{String(attrs.verification_method ?? "unknown")}</code>
              </dd>
            </div>
            <div>
              <dt>Recorded Receiver</dt>
              <dd>
                {String(attrs.receiver_model ?? "Unknown")} (fw{" "}
                {String(attrs.receiver_firmware ?? "?")})
              </dd>
            </div>
            <div>
              <dt>Galileo System Time</dt>
              <dd>
                WN {String(attrs.gst_week ?? "?")} · TOW {String(attrs.gst_tow_start ?? "?")}–
                {String(attrs.gst_tow_end ?? "?")} s
              </dd>
            </div>
            <div>
              <dt>Zero-NMA Subframes</dt>
              <dd>{String(attrs.unauthenticated_zero_nma_subframes ?? 0)}</dd>
            </div>
          </dl>
        </div>
      )}
    </section>
  );
}
