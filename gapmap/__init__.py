"""GapMap - find the riskiest undocumented code in a repository.

Pipeline: parse Python files -> build an import graph -> score risk
(incoming dependencies x lines of code) -> check which risky files are
mentioned in docs -> audit / explain / generate ADRs / report.
"""

__version__ = "0.1.0"
