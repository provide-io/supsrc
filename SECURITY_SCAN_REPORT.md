# Security Scan Report

**Date:** 2025-11-18
**Project:** supsrc
**Branch:** claude/security-scanners-review-01Ay56D6utKHQkEBiNVDFHWn

## Executive Summary

Comprehensive security scanning was performed on the supsrc codebase using multiple security scanners. The analysis includes:
- Static Application Security Testing (SAST) with Bandit and Semgrep
- Dependency vulnerability scanning with pip-audit and Safety
- Secret detection with GitLeaks and TruffleHog

### Overall Status: ⚠️ **ISSUES FOUND**

**Critical Findings:**
- 1 Private Key detected in repository
- 2 Dependency vulnerabilities
- 17 Code security issues (8 MEDIUM, 9 LOW)

---

## Scanner Results

### 1. Bandit (SecurityScanner) - Python SAST

**Status:** ❌ **FAILED** (Score: 51.0% - Below 80% threshold)

**Summary:**
- Files Scanned: 103
- Total Issues: 17
- HIGH: 0
- MEDIUM: 8
- LOW: 9

**Key Issues:**

1. **MEDIUM: Hardcoded Temp Directory Usage**
   - Location: `src/supsrc/cli/sui_cmds.py:83`
   - Location: `src/supsrc/cli/watch_cmds.py:235`
   - Issue: Probable insecure usage of temp file/directory
   - Recommendation: Use `tempfile.mkdtemp()` or `tempfile.NamedTemporaryFile()` with appropriate permissions

2. **LOW: Try-Except-Pass Blocks**
   - Multiple locations in `sui_cmds.py` (lines 92, 138, 215)
   - Issue: Silent exception handling can hide errors
   - Recommendation: Add logging or specific exception handling

**Report Location:** `.security-reports/bandit-summary.txt`

---

### 2. PipAudit - PyPI Vulnerability Scanner

**Status:** ❌ **FAILED**

**Summary:**
- Dependencies Scanned: 271
- Vulnerabilities Found: 2

**Vulnerabilities:**

1. **py 1.11.0 - ReDoS Vulnerability (PYSEC-2022-42969)**
   - CVE: CVE-2022-42969
   - Severity: Medium
   - Description: Remote attackers can conduct ReDoS (Regular expression Denial of Service) via crafted Subversion repository info data
   - Fix: No fix available yet (marked as no fix_versions)
   - Recommendation: Consider removing `py` dependency if possible, or monitor for updates

2. **uv 0.9.5 - ZIP Archive Parsing Differentials (GHSA-pqhf-p39g-3x64)**
   - Severity: Medium
   - Description: ZIP archives can be parsed differently across Python packaging tools, potentially enabling malicious packages
   - Fix: Upgrade to `uv >= 0.9.6`
   - Recommendation: **UPGRADE IMMEDIATELY** - This is a critical supply chain security issue

**Report Location:** `.security-reports/pip-audit.json`, `.security-reports/pip-audit.log`

---

### 3. Safety - PyUp Vulnerability Database

**Status:** ❌ **FAILED**

**Summary:**
- Packages Scanned: 272
- Vulnerabilities Found: 1
- Vulnerabilities Ignored: 0

**Details:**
One vulnerability detected in dependencies. The Safety database may overlap with pip-audit findings but uses a different vulnerability database (PyUp).

**Report Location:** `.security-reports/safety.json`, `.security-reports/safety.log`

---

### 4. Semgrep - Pattern-Based SAST

**Status:** ✅ **PASSED**

**Summary:**
- Files Scanned: 105
- Rules Applied: 1,062 (Community rules)
- Findings: 0

**Languages Analyzed:**
- Python: 243 rules on 104 files
- Multilang: 48 rules on 210 files

**Verdict:** No security issues found by Semgrep's comprehensive rule set including OWASP patterns.

**Report Location:** `.security-reports/semgrep.json`, `.security-reports/semgrep.log`

---

### 5. GitLeaks - Secret Detection

**Status:** ❌ **FAILED**

**Summary:**
- Commits Scanned: 1
- Secrets Found: 1

**Critical Finding:**

**🔴 PRIVATE KEY DETECTED**
- File: `keys/flavor-private.key`
- Type: Private Key
- Rule ID: private-key
- Commit: 2b3972ab115d5951d1f7a9db10e93d7d1c04c778
- Date: 2025-11-18T08:05:30Z
- Author: Tim <code@tim.life>
- Secret: REDACTED (for security)

**Recommendation:**
1. **IMMEDIATE ACTION REQUIRED:** Remove the private key from the repository
2. Revoke and rotate the compromised key if it's in active use
3. Add `keys/` to `.gitignore` to prevent future commits
4. Use git-filter-repo or BFG Repo-Cleaner to remove from git history
5. Consider using secret management tools (e.g., AWS Secrets Manager, HashiCorp Vault)

**Report Location:** `.security-reports/gitleaks.json`, `.security-reports/gitleaks.log`

---

### 6. TruffleHog - Deep Secret Detection

**Status:** ⚠️ **FINDINGS (Mostly False Positives)**

**Summary:**
- Total Findings: 95
- Most findings are in `.venv/` (dependencies and test files)
- Unverified secrets (no active verification attempted)

**Analysis:**
The majority of TruffleHog findings are:
- Example credentials in test files within `.venv/`
- URI patterns in HTTP library examples (httpx, hyperlink)
- Box API patterns in compiled binaries (pyre.bin)

These are considered **false positives** as they are not actual secrets in the source code.

**Report Location:** `.security-reports/trufflehog.log`

---

## Documentation Verification

### Security Scanners Guide Accuracy

The provided Security Scanners Guide was reviewed for accuracy against the current version of `provide-testkit` (v0.0.1114):

#### ❌ **Scanners Mentioned but NOT Available:**

1. **GitLeaksScanner** - Not implemented in provide-testkit
   - Workaround: Use GitLeaks CLI directly ✅ (now installed)

2. **PipAuditScanner** - Not implemented in provide-testkit
   - Workaround: Use pip-audit CLI directly ✅ (available via uv)

3. **SafetyScanner** - Not implemented in provide-testkit
   - Workaround: Use safety CLI directly ✅ (available via uv)

4. **SemgrepScanner** - Not implemented in provide-testkit
   - Workaround: Use semgrep CLI directly ✅ (available via uv)

5. **TruffleHogScanner** - Not implemented in provide-testkit
   - Workaround: Use TruffleHog CLI directly ✅ (now installed)

#### ✅ **Scanners Available:**

1. **SecurityScanner (Bandit)** - Fully implemented and working

**Conclusion:** The Security Scanners Guide appears to be documentation for exploratory features that are not yet implemented in the current release of provide-testkit. However, all underlying tools (bandit, pip-audit, safety, semgrep, gitleaks, trufflehog) are available and functional via CLI.

---

## Recommendations

### High Priority (Critical)

1. **Remove Private Key from Repository**
   - File: `keys/flavor-private.key`
   - Action: Delete file, add to `.gitignore`, remove from git history
   - Commands:
     ```bash
     git rm keys/flavor-private.key
     echo "keys/" >> .gitignore
     # Consider using git-filter-repo to remove from history
     ```
   - Timeline: **IMMEDIATE**

2. **Upgrade uv to Fix Supply Chain Vulnerability**
   - Current: uv 0.9.5
   - Required: uv >= 0.9.6
   - Issue: GHSA-pqhf-p39g-3x64 - ZIP archive parsing differentials
   - Commands:
     ```bash
     uv pip install --upgrade uv
     # Or reinstall uv via curl
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```
   - Timeline: **Within 24 hours**

3. **Address py Library ReDoS Vulnerability**
   - Current: py 1.11.0
   - Issue: PYSEC-2022-42969 - ReDoS via crafted SVN data
   - Note: No fix available yet, but impact is limited (only affects Subversion operations)
   - Action: Monitor for updates, consider alternatives if using SVN features
   - Timeline: Monitor monthly for updates

### Medium Priority

3. **Fix Temp Directory Security Issues**
   - Use Python's `tempfile` module with proper permissions
   - Affected files: `src/supsrc/cli/sui_cmds.py`, `src/supsrc/cli/watch_cmds.py`
   - Timeline: Within 1 week

4. **Improve Exception Handling**
   - Replace try-except-pass blocks with proper logging
   - Add specific exception types
   - Timeline: Within 2 weeks

### Low Priority

5. **Add Security Scanning to CI/CD**
   - Integrate Bandit, Semgrep, and dependency scanners into GitHub Actions
   - Block PRs with HIGH severity issues
   - Timeline: Within 1 month

6. **Implement Pre-commit Hooks**
   - Add gitleaks or TruffleHog as pre-commit hook
   - Prevent accidental secret commits
   - Timeline: Within 1 month

---

## Tools Installed

All security scanning tools are now available in the environment:

### Python-Based (via provide-testkit[all])
- ✅ Bandit 1.9.1
- ✅ pip-audit 2.9.0
- ✅ safety 3.7.0
- ✅ semgrep 1.79.0

### Binary Tools
- ✅ GitLeaks 8.18.0
- ✅ TruffleHog 3.63.2

### provide-testkit Status
- Version: 0.0.1114 (upgraded from 0.0.1100)
- provide-foundation: 0.0.1111 (upgraded from 0.0.1102)

---

## Files Generated

All security scan results are stored in `.security-reports/`:

```
.security-reports/
├── bandit-summary.txt       # Bandit scan summary
├── pip-audit.json           # pip-audit detailed results
├── pip-audit.log            # pip-audit console output
├── safety.json              # Safety scan detailed results
├── safety.log               # Safety console output
├── semgrep.json             # Semgrep findings (empty - no issues)
├── semgrep.log              # Semgrep console output
├── gitleaks.json            # GitLeaks findings (1 private key)
├── gitleaks.log             # GitLeaks console output
├── trufflehog.log           # TruffleHog findings (95 mostly false positives)
```

---

## Conclusion

The security scan reveals **one critical issue** (private key in repository) and **several medium-priority issues** (dependency vulnerabilities and code security practices). The codebase is generally well-structured with no major SAST findings from Semgrep, but requires immediate attention to the secret exposure and dependency updates.

**Next Steps:**
1. Address the private key issue immediately
2. Update vulnerable dependencies
3. Review and fix Bandit findings
4. Consider implementing automated security scanning in CI/CD pipeline

---

**Scan Executed By:** Claude Code Agent
**Report Generated:** 2025-11-18 08:29 UTC
