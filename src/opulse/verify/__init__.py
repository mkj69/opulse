"""Correctness machinery: the reference oracle and differential checks (spec section 9)."""

from opulse.verify.differential import Mismatch, boundary_values, check_operator
from opulse.verify.oracle import Oracle
from opulse.verify.records import VerificationError, verify_evaluation, verify_trace

__all__ = ["Mismatch", "Oracle", "VerificationError", "boundary_values", "check_operator",
           "verify_evaluation", "verify_trace"]
