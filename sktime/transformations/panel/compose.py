# -*- coding: utf-8 -*-
"""Meta Transformers module.

This module has meta-transformations that is build using the pre-existing
transformations as building blocks.
"""
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.base import clone
from sklearn.compose import ColumnTransformer as _ColumnTransformer

from sktime.datatypes._panel._convert import from_2d_array_to_nested
from sktime.transformations.base import (
    BaseTransformer,
    _PanelToPanelTransformer,
    _PanelToTabularTransformer,
    _SeriesToPrimitivesTransformer,
    _SeriesToSeriesTransformer,
)
from sktime.utils.multiindex import flatten_multiindex
from sktime.utils.validation.panel import check_X

__author__ = ["mloning", "sajaysurya", "fkiraly"]
__all__ = [
    "ColumnTransformer",
    "SeriesToPrimitivesRowTransformer",
    "SeriesToSeriesRowTransformer",
    "ColumnConcatenator",
]


class ColumnTransformer(_ColumnTransformer, _PanelToPanelTransformer):
    """Column-wise application of transformers.

    Applies transformations to columns of an array or pandas DataFrame. Simply
    takes the column transformer from sklearn
    and adds capability to handle pandas dataframe.

    This estimator allows different columns or column subsets of the input
    to be transformed separately and the features generated by each transformer
    will be concatenated to form a single feature space.
    This is useful for heterogeneous or columnar data, to combine several
    feature extraction mechanisms or transformations into a single transformer.

    Parameters
    ----------
    transformers : list of tuples
        List of (name, transformer, column(s)) tuples specifying the
        transformer objects to be applied to subsets of the data.
        name : string
            Like in Pipeline and FeatureUnion, this allows the transformer and
            its parameters to be set using ``set_params`` and searched in grid
            search.
        transformer : estimator or {"passthrough", "drop"}
            Estimator must support `fit` and `transform`. Special-cased
            strings "drop" and "passthrough" are accepted as well, to
            indicate to drop the columns or to pass them through untransformed,
            respectively.
        column(s) : str or int, array-like of string or int, slice, boolean
        mask array or callable
            Indexes the data on its second axis. Integers are interpreted as
            positional columns, while strings can reference DataFrame columns
            by name.  A scalar string or int should be used where
            ``transformer`` expects X to be a 1d array-like (vector),
            otherwise a 2d array will be passed to the transformer.
            A callable is passed the input data `X` and can return any of the
            above.
    remainder : {"drop", "passthrough"} or estimator, default "drop"
        By default, only the specified columns in `transformations` are
        transformed and combined in the output, and the non-specified
        columns are dropped. (default of ``"drop"``).
        By specifying ``remainder="passthrough"``, all remaining columns that
        were not specified in `transformations` will be automatically passed
        through. This subset of columns is concatenated with the output of
        the transformations.
        By setting ``remainder`` to be an estimator, the remaining
        non-specified columns will use the ``remainder`` estimator. The
        estimator must support `fit` and `transform`.
    sparse_threshold : float, default = 0.3
        If the output of the different transformations contains sparse matrices,
        these will be stacked as a sparse matrix if the overall density is
        lower than this value. Use ``sparse_threshold=0`` to always return
        dense.  When the transformed output consists of all dense data, the
        stacked result will be dense, and this keyword will be ignored.
    n_jobs : int or None, optional (default=None)
        Number of jobs to run in parallel.
        ``None`` means 1 unless in a :obj:`joblib.parallel_backend` context.
        ``-1`` means using all processors.
    transformer_weights : dict, optional
        Multiplicative weights for features per transformer. The output of the
        transformer is multiplied by these weights. Keys are transformer names,
        values the weights.
    preserve_dataframe : boolean
        If True, pandas dataframe is returned.
        If False, numpy array is returned.


    Attributes
    ----------
    transformers_ : list
        The collection of fitted transformations as tuples of
        (name, fitted_transformer, column). `fitted_transformer` can be an
        estimator, "drop", or "passthrough". In case there were no columns
        selected, this will be the unfitted transformer.
        If there are remaining columns, the final element is a tuple of the
        form:
        ("remainder", transformer, remaining_columns) corresponding to the
        ``remainder`` parameter. If there are remaining columns, then
        ``len(transformers_)==len(transformations)+1``, otherwise
        ``len(transformers_)==len(transformations)``.
    named_transformers_ : Bunch object, a dictionary with attribute access
        Read-only attribute to access any transformer by given name.
        Keys are transformer names and values are the fitted transformer
        objects.
    sparse_output_ : bool
        Boolean flag indicating wether the output of ``transform`` is a
        sparse matrix or a dense numpy array, which depends on the output
        of the individual transformations and the `sparse_threshold` keyword.
    """

    def __init__(
        self,
        transformers,
        remainder="drop",
        sparse_threshold=0.3,
        n_jobs=1,
        transformer_weights=None,
        preserve_dataframe=True,
    ):
        super(ColumnTransformer, self).__init__(
            transformers=transformers,
            remainder=remainder,
            sparse_threshold=sparse_threshold,
            n_jobs=n_jobs,
            transformer_weights=transformer_weights,
        )
        BaseTransformer.__init__(self)
        self.preserve_dataframe = preserve_dataframe
        self._is_fitted = False

    def _hstack(self, Xs):
        """
        Stacks X horizontally.

        Supports input types (X): list of numpy arrays, sparse arrays and
        DataFrames
        """
        types = set(type(X) for X in Xs)

        if self.sparse_output_:
            return sparse.hstack(Xs).tocsr()
        if self.preserve_dataframe and (pd.Series in types or pd.DataFrame in types):
            vars = [y for x in self.transformers for y in x[2]]
            vars_unique = len(set(vars)) == len(vars)
            names = [str(x[0]) for x in self.transformers]
            if vars_unique:
                return pd.concat(Xs, axis="columns")
            else:
                Xt = pd.concat(Xs, axis="columns", keys=names)
                Xt.columns = flatten_multiindex(Xt.columns)
                return Xt
        return np.hstack(Xs)

    def _validate_output(self, result):
        """Validate output of every transformer.

        Ensure that the output of each transformer is 2D. Otherwise
        hstack can raise an error or produce incorrect results.

        Output can also be a pd.Series which is actually a 1D
        """
        names = [
            name for name, _, _, _ in self._iter(fitted=True, replace_strings=True)
        ]
        for Xs, name in zip(result, names):
            if not (getattr(Xs, "ndim", 0) == 2 or isinstance(Xs, pd.Series)):
                raise ValueError(
                    "The output of the '{0}' transformer should be 2D (scipy "
                    "matrix, array, or pandas DataFrame).".format(name)
                )

    @classmethod
    def get_test_params(cls):
        """Return testing parameter settings for the estimator.

        Returns
        -------
        params : dict or list of dict, default = {}
            Parameters to create testing instances of the class
            Each dict are parameters to construct an "interesting" test instance, i.e.,
            `MyClass(**params)` or `MyClass(**params[i])` creates a valid test instance.
            `create_test_instance` uses the first (or only) dictionary in `params`
        """
        from sklearn.preprocessing import StandardScaler

        from sktime.transformations.panel.compose import SeriesToSeriesRowTransformer

        SERIES_TO_SERIES_TRANSFORMER = StandardScaler()
        TRANSFORMERS = [
            (
                "transformer1",
                SeriesToSeriesRowTransformer(
                    SERIES_TO_SERIES_TRANSFORMER, check_transformer=False
                ),
            ),
            (
                "transformer2",
                SeriesToSeriesRowTransformer(
                    SERIES_TO_SERIES_TRANSFORMER, check_transformer=False
                ),
            ),
        ]

        return {
            "transformers": [(name, estimator, [0]) for name, estimator in TRANSFORMERS]
        }

    def fit(self, X, y=None):
        """Fit the transformer."""
        X = check_X(X, coerce_to_pandas=True)
        super(ColumnTransformer, self).fit(X, y)
        self._is_fitted = True
        return self

    def transform(self, X, y=None):
        """Transform the data."""
        self.check_is_fitted()
        X = check_X(X, coerce_to_pandas=True)
        return super(ColumnTransformer, self).transform(X)

    def fit_transform(self, X, y=None):
        """Fit and transform, shorthand."""
        # Wrap fit_transform to set _is_fitted attribute
        Xt = super(ColumnTransformer, self).fit_transform(X, y)
        self._is_fitted = True
        return Xt


class ColumnConcatenator(BaseTransformer):
    """Concatenate multivariate series to a long univariate series.

    Transformer that concatenates multivariate time series/panel data
    into long univariate time series/panel
        data by simply concatenating times series in time.
    """

    _tags = {
        "scitype:transform-input": "Series",
        # what is the scitype of X: Series, or Panel
        "scitype:transform-output": "Series",
        # what scitype is returned: Primitives, Series, Panel
        "scitype:instancewise": False,  # is this an instance-wise transform?
        "X_inner_mtype": ["pd-multiindex", "pd_multiindex_hier"],
        # which mtypes do _fit/_predict support for X?
        "y_inner_mtype": "None",  # which mtypes do _fit/_predict support for X?
        "fit_is_empty": True,  # is fit empty and can be skipped? Yes = True
    }

    def _transform(self, X, y=None):
        """Transform the data.

        Concatenate multivariate time series/panel data into long
        univariate time series/panel
        data by simply concatenating times series in time.

        Parameters
        ----------
        X : nested pandas DataFrame of shape [n_samples, n_features]
            Nested dataframe with time-series in cells.

        Returns
        -------
        Xt : pandas DataFrame
          Transformed pandas DataFrame with same number of rows and single
          column
        """
        Xst = pd.DataFrame(X.stack())
        Xt = Xst.swaplevel(-2, -1).sort_index().droplevel(-2)

        # the above has the right structure, but the wrong indes
        # the time index is in general non-unique now, we replace it by integer index
        inst_idx = Xt.index.get_level_values(0)
        t_idx = [range(len(Xt.loc[x])) for x in inst_idx.unique()]
        t_idx = np.concatenate(t_idx)

        Xt.index = pd.MultiIndex.from_arrays([inst_idx, t_idx])
        Xt.index.names = X.index.names
        return Xt


def _from_nested_to_series(x):
    """Un-nest series."""
    if x.shape[0] == 1:
        return np.asarray(x.iloc[0]).reshape(-1, 1)
    else:
        data = x.tolist()
        if not len(set([len(x) for x in data])) == 1:
            raise NotImplementedError(
                "Unequal length multivariate data are not supported yet."
            )
        return pd.DataFrame(data).T


class _RowTransformer(BaseTransformer):
    """Base class for RowTransformer."""

    _tags = {"fit_is_empty": True}

    def __init__(self, transformer, check_transformer=True):
        self.transformer = transformer
        self.check_transformer = check_transformer
        super(_RowTransformer, self).__init__()

    def _check_transformer(self):
        """Check transformer type compatibility."""
        assert hasattr(self, "_valid_transformer_type")
        if self.check_transformer and not isinstance(
            self.transformer, self._valid_transformer_type
        ):
            raise TypeError(
                f"transformer must be a " f"{self._valid_transformer_type.__name__}"
            )

    def _prepare(self, X):
        self.check_is_fitted()
        self._check_transformer()
        X = check_X(X, coerce_to_numpy=True)
        self.transformer_ = [clone(self.transformer) for _ in range(X.shape[0])]
        return X


class SeriesToPrimitivesRowTransformer(_RowTransformer, _PanelToTabularTransformer):
    """Series-to-primitives row transformer."""

    _valid_transformer_type = _SeriesToPrimitivesTransformer

    def transform(self, X, y=None):
        """Transform the data."""
        X = self._prepare(X)
        Xt = np.zeros(X.shape[:2])
        for i in range(X.shape[0]):
            # We need to maintain the number of dimension when we slice, so that we
            # still pass a 2-dimensional array to the transformer
            Xt[i] = self.transformer_[i].fit_transform(X[i].T)
        return pd.DataFrame(Xt)

    @classmethod
    def get_test_params(cls, parameter_set="default"):
        """Return testing parameter settings for the estimator.

        Parameters
        ----------
        parameter_set : str, default="default"
            Name of the set of test parameters to return, for use in tests. If no
            special parameters are defined for a value, will return `"default"` set.

        Returns
        -------
        params : dict or list of dict, default={}
            Parameters to create testing instances of the class.
            Each dict are parameters to construct an "interesting" test instance, i.e.,
            `MyClass(**params)` or `MyClass(**params[i])` creates a valid test instance.
            `create_test_instance` uses the first (or only) dictionary in `params`.
        """
        import numpy as np
        from sklearn.preprocessing import FunctionTransformer

        trafo = FunctionTransformer(np.mean, kw_args={"axis": 0}, check_inverse=False)
        return {"transformer": trafo, "check_transformer": False}


class SeriesToSeriesRowTransformer(_RowTransformer, _PanelToPanelTransformer):
    """Series-to-series row transformer."""

    _valid_transformer_type = _SeriesToSeriesTransformer

    def transform(self, X, y=None):
        """Transform the data."""
        X = self._prepare(X)
        xts = list()
        for i in range(X.shape[0]):
            xt = self.transformer_[i].fit_transform(X[i].T)
            xts.append(from_2d_array_to_nested(xt.T).T)
        Xt = pd.concat(xts, axis=0)
        if isinstance(X, pd.DataFrame):
            Xt.index = X.index
        else:
            Xt = Xt.reset_index(drop=True)
        return Xt

    @classmethod
    def get_test_params(cls, parameter_set="default"):
        """Return testing parameter settings for the estimator.

        Parameters
        ----------
        parameter_set : str, default="default"
            Name of the set of test parameters to return, for use in tests. If no
            special parameters are defined for a value, will return `"default"` set.

        Returns
        -------
        params : dict or list of dict, default={}
            Parameters to create testing instances of the class.
            Each dict are parameters to construct an "interesting" test instance, i.e.,
            `MyClass(**params)` or `MyClass(**params[i])` creates a valid test instance.
            `create_test_instance` uses the first (or only) dictionary in `params`.
        """
        from sklearn.preprocessing import StandardScaler

        return {"transformer": StandardScaler(), "check_transformer": False}


def make_row_transformer(transformer, transformer_type=None, **kwargs):
    """Cate InstanceTransformer based on transform type, factory function."""
    if transformer_type is not None:
        valid_transformer_types = ("series-to-series", "series-to-primitives")
        if transformer_type not in valid_transformer_types:
            raise ValueError(
                f"Invalid `transformer_type`. Please choose one of "
                f"{valid_transformer_types}."
            )
    else:
        if isinstance(transformer, _SeriesToSeriesTransformer):
            transformer_type = "series-to-series"
        elif isinstance(transformer, _SeriesToPrimitivesTransformer):
            transformer_type = "series-to-primitives"
        else:
            raise TypeError(
                "transformer type not understood. Please specify `transformer_type`."
            )
    if transformer_type == "series-to-series":
        return SeriesToSeriesRowTransformer(transformer, **kwargs)
    else:
        return SeriesToPrimitivesRowTransformer(transformer, **kwargs)
