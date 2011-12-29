"""
=======================================
Pixel importances with forests of trees
=======================================

This example shows the use of forests of trees to evaluate the importance
of the pixels in an image classification task (faces). The hotter the pixel,
the more important.
"""
print __doc__

import pylab as pl

from sklearn.datasets import fetch_olivetti_faces
from sklearn.ensemble import ExtraTreesClassifier

# Loading the digits dataset
data = fetch_olivetti_faces()
X = data.images.reshape((len(data.images), -1))
y = data.target

mask = y < 5 # Limit to 5 classes
X = X[mask]
y = y[mask]

# Build a forest and compute the pixel importances
forest = ExtraTreesClassifier(n_estimators=1000,
                              max_features=128,
                              compute_importances=True,
                              random_state=0)

forest.fit(X, y)
importances = forest.feature_importances_
importances = importances.reshape(data.images[0].shape)

# Plot pixel importances
pl.matshow(importances, cmap=pl.cm.hot)
pl.colorbar()
pl.title("Pixel importances with forests of trees")
pl.show()