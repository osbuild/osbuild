"""
Exceptions for the osbuild solver
"""


class SolverException(Exception):
    pass


class GPGKeyReadError(SolverException):
    pass


class TransactionError(SolverException):
    pass


class RepoError(SolverException):
    pass


class NoReposError(SolverException):
    pass


class MarkingError(SolverException):
    pass


class DepsolveError(SolverException):
    pass


class InvalidRequestError(SolverException):
    pass
