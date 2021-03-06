"""Testing for K-means"""

import numpy as np
from scipy import sparse as sp
from numpy.testing import assert_equal
from numpy.testing import assert_array_equal
from numpy.testing import assert_array_almost_equal
from nose import SkipTest
from nose.tools import assert_almost_equal
from nose.tools import assert_raises
from nose.tools import assert_true

from sklearn.metrics.cluster import v_measure_score
from sklearn.cluster import KMeans
from sklearn.cluster import MiniBatchKMeans
from sklearn.cluster.k_means_ import _labels_inertia
from sklearn.cluster.k_means_ import _mini_batch_step
from sklearn.cluster._k_means import csr_row_norm_l2
from sklearn.datasets.samples_generator import make_blobs


# non centered, sparse centers to check the
centers = np.array([
    [0.0, 5.0, 0.0, 0.0, 0.0],
    [1.0, 1.0, 4.0, 0.0, 0.0],
    [1.0, 0.0, 0.0, 5.0, 1.0],
])
n_samples = 100
n_clusters, n_features = centers.shape
X, true_labels = make_blobs(n_samples=n_samples, centers=centers,
                            cluster_std=1., random_state=42)
X_csr = sp.csr_matrix(X)


def test_square_norms():
    x_squared_norms = (X ** 2).sum(axis=1)
    x_squared_norms_from_csr = csr_row_norm_l2(X_csr)
    assert_array_almost_equal(x_squared_norms,
                              x_squared_norms_from_csr, 5)


def test_labels_assignement_and_inertia():
    # pure numpy implementation as easily auditable reference gold
    # implementation
    rng = np.random.RandomState(42)
    noisy_centers = centers + rng.normal(size=centers.shape)
    labels_gold = - np.ones(n_samples, dtype=np.int)
    mindist = np.empty(n_samples)
    mindist.fill(np.infty)
    for center_id in range(n_clusters):
        dist = np.sum((X - noisy_centers[center_id]) ** 2, axis=1)
        labels_gold[dist < mindist] = center_id
        mindist = np.minimum(dist, mindist)
    inertia_gold = mindist.sum()
    assert_true((mindist >= 0.0).all())
    assert_true((labels_gold != -1).all())

    # perform label assignement using the dense array input
    x_squared_norms = (X ** 2).sum(axis=1)
    labels_array, inertia_array = _labels_inertia(
        X, x_squared_norms, noisy_centers)
    assert_array_almost_equal(inertia_array, inertia_gold)
    assert_array_equal(labels_array, labels_gold)

    # perform label assignement using the sparse CSR input
    x_squared_norms_from_csr = csr_row_norm_l2(X_csr)
    labels_csr, inertia_csr = _labels_inertia(
        X_csr, x_squared_norms_from_csr, noisy_centers)
    assert_array_almost_equal(inertia_csr, inertia_gold)
    assert_array_equal(labels_csr, labels_gold)


def test_minibatch_update_consistency():
    """Check that dense and sparse minibatch update give the same results"""
    rng = np.random.RandomState(42)
    old_centers = centers + rng.normal(size=centers.shape)

    new_centers = old_centers.copy()
    new_centers_csr = old_centers.copy()

    counts = np.zeros(new_centers.shape[0], dtype=np.int32)
    counts_csr = np.zeros(new_centers.shape[0], dtype=np.int32)

    x_squared_norms = (X ** 2).sum(axis=1)
    x_squared_norms_csr = csr_row_norm_l2(X_csr, squared=True)

    buffer = np.zeros(centers.shape[1], dtype=np.double)
    buffer_csr = np.zeros(centers.shape[1], dtype=np.double)

    # extract a small minibatch
    X_mb = X[:10]
    X_mb_csr = X_csr[:10]
    x_mb_squared_norms = x_squared_norms[:10]
    x_mb_squared_norms_csr = x_squared_norms_csr[:10]

    # step 1: compute the dense minibatch update
    old_inertia, incremental_diff = _mini_batch_step(
        X_mb, x_mb_squared_norms, new_centers, counts,
        buffer, 1)
    assert_true(old_inertia > 0.0)

    # compute the new inertia on the same batch to check that it decreased
    labels, new_inertia = _labels_inertia(
        X_mb, x_mb_squared_norms, new_centers)
    assert_true(new_inertia > 0.0)
    assert_true(new_inertia < old_inertia)

    # check that the incremental difference computation is matching the
    # final observed value
    effective_diff = np.sum((new_centers - old_centers) ** 2)
    assert_almost_equal(incremental_diff, effective_diff)

    # step 2: compute the sparse minibatch update
    old_inertia_csr, incremental_diff_csr = _mini_batch_step(
        X_mb_csr, x_mb_squared_norms_csr, new_centers_csr, counts_csr,
        buffer_csr, 1)
    assert_true(old_inertia_csr > 0.0)

    # compute the new inertia on the same batch to check that it decreased
    labels_csr, new_inertia_csr = _labels_inertia(
        X_mb_csr, x_mb_squared_norms_csr, new_centers_csr)
    assert_true(new_inertia_csr > 0.0)
    assert_true(new_inertia_csr < old_inertia_csr)

    # check that the incremental difference computation is matching the
    # final observed value
    effective_diff = np.sum((new_centers_csr - old_centers) ** 2)
    assert_almost_equal(incremental_diff_csr, effective_diff)

    # step 3: check that sparse and dense updates lead to the same results
    assert_array_equal(labels, labels_csr)
    assert_array_almost_equal(new_centers, new_centers_csr)
    assert_almost_equal(incremental_diff, incremental_diff_csr)
    assert_almost_equal(old_inertia, old_inertia_csr)
    assert_almost_equal(new_inertia, new_inertia_csr)


def _check_fitted_model(km):
    centers = km.cluster_centers_
    assert_equal(centers.shape, (n_clusters, n_features))

    labels = km.labels_
    assert_equal(np.unique(labels).shape[0], n_clusters)

    # check that the labels assignements are perfect (up to a permutation)
    assert_equal(v_measure_score(true_labels, labels), 1.0)
    assert_true(km.inertia_ > 0.0)

    # check error on dataset being too small
    assert_raises(ValueError, km.fit, [[0., 1.]])


def test_k_means_plus_plus_init():
    k_means = KMeans(init="k-means++", k=n_clusters, random_state=42).fit(X)
    _check_fitted_model(k_means)


def _get_mac_os_version():
    import platform
    mac_version, _, _ = platform.mac_ver()
    if mac_version:
        # turn something like '10.7.3' into '10.7'
        return '.'.join(mac_version.split('.')[:2])


def test_k_means_plus_plus_init_2_jobs():
    if _get_mac_os_version() == '10.7':
        raise SkipTest('Multi-process bug in Mac OS X Lion (see issue #636)')
    k_means = KMeans(init="k-means++", k=n_clusters, n_jobs=2,
                     random_state=42).fit(X)
    _check_fitted_model(k_means)


def test_k_means_plus_plus_init_sparse():
    k_means = KMeans(init="k-means++", k=n_clusters, random_state=42)
    k_means.fit(X_csr)
    _check_fitted_model(k_means)


def test_k_means_random_init():
    k_means = KMeans(init="random", k=n_clusters, random_state=42).fit(X)
    _check_fitted_model(k_means)


def test_k_means_random_init_sparse():
    k_means = KMeans(init="random", k=n_clusters, random_state=42).fit(X_csr)
    _check_fitted_model(k_means)


def test_k_means_plus_plus_init_not_precomputed():
    k_means = KMeans(init="k-means++", k=n_clusters, random_state=42,
                     precompute_distances=False).fit(X)
    _check_fitted_model(k_means)


def test_k_means_random_init_not_precomputed():
    k_means = KMeans(init="random", k=n_clusters, random_state=42,
                     precompute_distances=False).fit(X)
    _check_fitted_model(k_means)


def test_k_means_perfect_init():
    k_means = KMeans(init=centers.copy(), k=n_clusters, random_state=42,
                     n_init=1)
    k_means.fit(X)
    _check_fitted_model(k_means)


def test_mb_k_means_plus_plus_init_dense_array():
    mb_k_means = MiniBatchKMeans(init="k-means++", k=n_clusters,
                                 random_state=42)
    mb_k_means.fit(X)
    _check_fitted_model(mb_k_means)


def test_mb_k_means_plus_plus_init_sparse_matrix():
    mb_k_means = MiniBatchKMeans(init="k-means++", k=n_clusters,
                                 random_state=42)
    mb_k_means.fit(X_csr)
    _check_fitted_model(mb_k_means)


def test_minibatch_k_means_random_init_dense_array():
    # increase n_init to make random init stable enough
    mb_k_means = MiniBatchKMeans(init="random", k=n_clusters,
                                 random_state=42, n_init=10).fit(X)
    _check_fitted_model(mb_k_means)


def test_minibatch_k_means_random_init_sparse_csr():
    # increase n_init to make random init stable enough
    mb_k_means = MiniBatchKMeans(init="random", k=n_clusters,
                                 random_state=42, n_init=10).fit(X_csr)
    _check_fitted_model(mb_k_means)


def test_minibatch_k_means_perfect_init_dense_array():
    mb_k_means = MiniBatchKMeans(init=centers.copy(), k=n_clusters,
                                 random_state=42).fit(X)
    _check_fitted_model(mb_k_means)


def test_minibatch_k_means_perfect_init_sparse_csr():
    mb_k_means = MiniBatchKMeans(init=centers.copy(), k=n_clusters,
                                 random_state=42).fit(X_csr)
    _check_fitted_model(mb_k_means)


def test_sparse_mb_k_means_callable_init():

    def test_init(X, k, random_state):
        return centers

    mb_k_means = MiniBatchKMeans(init=test_init, random_state=42).fit(X_csr)
    _check_fitted_model(mb_k_means)


def test_mini_batch_k_means_random_init_partial_fit():
    km = MiniBatchKMeans(k=n_clusters, init="random", random_state=42)

    # use the partial_fit API for online learning
    for X_minibatch in np.array_split(X, 10):
        km.partial_fit(X_minibatch)

    # compute the labeling on the complete dataset
    labels = km.predict(X)
    assert_equal(v_measure_score(true_labels, labels), 1.0)


def test_minibatch_default_init_size():
    mb_k_means = MiniBatchKMeans(init=centers.copy(), k=n_clusters,
                                 random_state=42).fit(X)
    assert_equal(mb_k_means.init_size, 3 * mb_k_means.batch_size)
    _check_fitted_model(mb_k_means)


def test_minibatch_set_init_size():
    mb_k_means = MiniBatchKMeans(init=centers.copy(), k=n_clusters,
                                 init_size=666, random_state=42).fit(X)
    assert_equal(mb_k_means.init_size, 666)
    _check_fitted_model(mb_k_means)


def test_k_means_invalid_init():
    k_means = KMeans(init="invalid", n_init=1, k=n_clusters)
    assert_raises(ValueError, k_means.fit, X)


def test_k_means_copyx():
    """Check if copy_x=False returns nearly equal X after de-centering."""
    my_X = X.copy()
    k_means = KMeans(copy_x=False, k=n_clusters, random_state=42).fit(my_X)
    _check_fitted_model(k_means)

    # check if my_X is centered
    assert_array_almost_equal(my_X, X)


def test_k_means_non_collapsed():
    """Check k_means with a bad initialization does not yield a singleton

    Starting with bad centers that are quickly ignored should not
    result in a repositioning of the centers to the center of mass that
    would lead to collapsed centers which in turns make the clustering
    dependent of the numerical unstabilities.
    """
    my_X = np.array([[1.1, 1.1], [0.9, 1.1], [1.1, 0.9], [0.9, 1.1]])
    array_init = np.array([[1.0, 1.0], [5.0, 5.0], [-5.0, -5.0]])
    k_means = KMeans(init=array_init, k=3, random_state=42, n_init=1)
    k_means.fit(my_X)

    # centers must not been collapsed
    assert_equal(len(np.unique(k_means.labels_)), 3)

    centers = k_means.cluster_centers_
    assert_true(np.linalg.norm(centers[0] - centers[1]) >= 0.1)
    assert_true(np.linalg.norm(centers[0] - centers[2]) >= 0.1)
    assert_true(np.linalg.norm(centers[1] - centers[2]) >= 0.1)


def test_predict():
    k_means = KMeans(k=n_clusters, random_state=42).fit(X)

    # sanity check: predict centroid labels
    pred = k_means.predict(k_means.cluster_centers_)
    assert_array_equal(pred, np.arange(n_clusters))

    # sanity check: re-predict labeling for training set samples
    pred = k_means.predict(X)
    assert_array_equal(k_means.predict(X), k_means.labels_)


def test_score():
    s1 = KMeans(k=n_clusters, max_iter=1, random_state=42).fit(X).score(X)
    s2 = KMeans(k=n_clusters, max_iter=10, random_state=42).fit(X).score(X)
    assert_true(s2 > s1)


def test_predict_minibatch_dense_input():
    mb_k_means = MiniBatchKMeans(k=n_clusters, random_state=40).fit(X)

    # sanity check: predict centroid labels
    pred = mb_k_means.predict(mb_k_means.cluster_centers_)
    assert_array_equal(pred, np.arange(n_clusters))

    # sanity check: re-predict labeling for training set samples
    pred = mb_k_means.predict(X)
    assert_array_equal(mb_k_means.predict(X), mb_k_means.labels_)


def test_predict_minibatch_kmeanspp_init_sparse_input():
    mb_k_means = MiniBatchKMeans(k=n_clusters, init='k-means++',
                                 n_init=10).fit(X_csr)

    # sanity check: re-predict labeling for training set samples
    assert_array_equal(mb_k_means.predict(X_csr), mb_k_means.labels_)

    # sanity check: predict centroid labels
    pred = mb_k_means.predict(mb_k_means.cluster_centers_)
    assert_array_equal(pred, np.arange(n_clusters))

    # check that models trained on sparse input also works for dense input at
    # predict time
    assert_array_equal(mb_k_means.predict(X), mb_k_means.labels_)


def test_predict_minibatch_random_init_sparse_input():
    mb_k_means = MiniBatchKMeans(k=n_clusters, init='random',
                                 n_init=10).fit(X_csr)

    # sanity check: re-predict labeling for training set samples
    assert_array_equal(mb_k_means.predict(X_csr), mb_k_means.labels_)

    # sanity check: predict centroid labels
    pred = mb_k_means.predict(mb_k_means.cluster_centers_)
    assert_array_equal(pred, np.arange(n_clusters))

    # check that models trained on sparse input also works for dense input at
    # predict time
    assert_array_equal(mb_k_means.predict(X), mb_k_means.labels_)


def test_input_dtypes():
    X_list = [[0, 0], [10, 10], [12, 9], [-1, 1], [2, 0], [8, 10]]
    X_int = np.array(X_list, dtype=np.int32)
    X_int_csr = sp.csr_matrix(X_int)
    init_int = X_int[:2]

    fitted_models = [
        KMeans(k=2).fit(X_list),
        KMeans(k=2).fit(X_int),
        KMeans(k=2, init=init_int, n_init=1).fit(X_list),
        KMeans(k=2, init=init_int, n_init=1).fit(X_int),
        # mini batch kmeans is very unstable on such a small dataset hence
        # we use many inits
        MiniBatchKMeans(k=2, n_init=10, batch_size=2).fit(X_list),
        MiniBatchKMeans(k=2, n_init=10, batch_size=2).fit(X_int),
        MiniBatchKMeans(k=2, n_init=10, batch_size=2).fit(X_int_csr),
        MiniBatchKMeans(k=2, batch_size=2, init=init_int).fit(X_list),
        MiniBatchKMeans(k=2, batch_size=2, init=init_int).fit(X_int),
        MiniBatchKMeans(k=2, batch_size=2, init=init_int).fit(X_int_csr),
    ]
    expected_labels = [0, 1, 1, 0, 0, 1]
    scores = np.array([v_measure_score(expected_labels, km.labels_)
                       for km in fitted_models])
    assert_array_equal(scores, np.ones(scores.shape[0]))


def test_transform():
    k_means = KMeans(k=n_clusters)
    k_means.fit(X)
    X_new = k_means.transform(k_means.cluster_centers_)

    for c in range(n_clusters):
        assert_equal(X_new[c, c], 0)
        for c2 in range(n_clusters):
            if c != c2:
                assert_true(X_new[c, c2] > 0)


def test_n_init():
    """Check that increasing the number of init increases the quality"""
    n_runs = 5
    n_init_range = [1, 5, 10]
    inertia = np.zeros((len(n_init_range), n_runs))
    for i, n_init in enumerate(n_init_range):
        for j in range(n_runs):
            km = KMeans(k=n_clusters, init="random", n_init=n_init,
                        random_state=j).fit(X)
            inertia[i, j] = km.inertia_

    inertia = inertia.mean(axis=1)
    failure_msg = ("Inertia %r should be decreasing"
                   " when n_init is increasing.") % list(inertia)
    for i in range(len(n_init_range) - 1):
        assert_true(inertia[i] >= inertia[i + 1], failure_msg)
