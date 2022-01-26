#!/usr/bin/env python3 -u
# -*- coding: utf-8 -*-
# copyright: sktime developers, BSD-3-Clause License (see LICENSE file)
"""Validation functions."""

__all__ = [
    "is_int",
    "is_float",
    "is_timedelta",
    "is_date_offset",
    "is_timedelta_or_date_offset",
    "check_n_jobs",
    "check_window_length",
]
__author__ = ["Markus Löning", "Taiwo Owoseni", "khrapovs"]

import os
from datetime import timedelta
from typing import Union

import numpy as np
import pandas as pd

ACCEPTED_TIMEDELTA_TYPES = pd.Timedelta, timedelta, np.timedelta64
ACCEPTED_DATEOFFSET_TYPES = pd.DateOffset
ACCEPTED_WINDOW_LENGTH_TYPES = Union[
    int, float, Union[ACCEPTED_TIMEDELTA_TYPES], Union[ACCEPTED_DATEOFFSET_TYPES]
]
NON_FLOAT_WINDOW_LENGTH_TYPES = Union[
    int, Union[ACCEPTED_TIMEDELTA_TYPES], Union[ACCEPTED_DATEOFFSET_TYPES]
]


def is_int(x) -> bool:
    """Check if x is of integer type, but not boolean."""
    # boolean are subclasses of integers in Python, so explicitly exclude them
    return isinstance(x, (int, np.integer)) and not isinstance(x, bool)


def is_float(x) -> bool:
    """Check if x is of float type."""
    return isinstance(x, (float, np.floating))


def is_timedelta(x) -> bool:
    """Check if x is of timedelta type."""
    return isinstance(x, ACCEPTED_TIMEDELTA_TYPES)


def is_date_offset(x) -> bool:
    """Check if x is of pd.DateOffset type."""
    return isinstance(x, ACCEPTED_DATEOFFSET_TYPES)


def is_timedelta_or_date_offset(x) -> bool:
    """Check if x is of timedelta or pd.DateOffset type."""
    return is_timedelta(x=x) or is_date_offset(x=x)


def check_n_jobs(n_jobs: int) -> int:
    """Check `n_jobs` parameter according to the scikit-learn convention.

    Parameters
    ----------
    n_jobs : int, positive or -1
        The number of jobs for parallelization.

    Returns
    -------
    n_jobs : int
        Checked number of jobs.
    """
    # scikit-learn convention
    # https://scikit-learn.org/stable/glossary.html#term-n-jobs
    if n_jobs is None:
        return 1
    elif not is_int(n_jobs):
        raise ValueError(f"`n_jobs` must be None or an integer, but found: {n_jobs}")
    elif n_jobs < 0:
        return os.cpu_count() - n_jobs + 1
    else:
        return n_jobs


def check_window_length(
    window_length: ACCEPTED_WINDOW_LENGTH_TYPES,
    n_timepoints: int = None,
    name: str = "window_length",
) -> NON_FLOAT_WINDOW_LENGTH_TYPES:
    """Validate window length.

    Parameters
    ----------
    window_length: positive int, positive float in (0, 1), positive timedelta,
        positive pd.DateOffset, or None
        The window length:
        - If int, the total number of time points.
        - If float, the fraction of time points relative to `n_timepoints`.
        - If timedelta, length in corresponding time units
        - If pd.DateOffset, length in corresponding time units following calendar rules
    n_timepoints: positive int, optional (default=None)
        The number of time points to which to apply `window_length` when
        passed as a float (fraction). Will be ignored if `window_length` is
        an integer.
    name: str
        Name of argument for error messages.

    Returns
    -------
    window_length: int or timedelta or pd.DateOffset
    """
    if window_length is None:
        return window_length

    elif is_int(window_length) and window_length >= 1:
        return window_length

    elif is_float(window_length) and 0 < window_length < 1:
        # Check `n_timepoints`.
        if not is_int(n_timepoints) or n_timepoints < 2:
            raise ValueError(
                f"`n_timepoints` must be a positive integer, but found:"
                f" {n_timepoints}."
            )

        # Compute fraction relative to `n_timepoints`.
        return int(np.ceil(window_length * n_timepoints))

    elif is_timedelta(window_length) and window_length > timedelta(0):
        return window_length

    elif is_date_offset(window_length) and pd.Timestamp(
        0
    ) + window_length > pd.Timestamp(0):
        return window_length

    else:
        raise ValueError(
            f"`{name}` must be a positive integer >= 1, or"
            f"float in (0, 1) or None, but found: {window_length}."
        )
