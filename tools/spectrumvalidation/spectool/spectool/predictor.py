#!/usr/bin/env python
# MIT License
#
# Copyright (c) 2019 Miklos Maroti
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# This file is a part of the CIRN Interaction Language.
from __future__ import print_function, division
import logging
import numpy as np
import pandas as pd
import pyflux as pf


def predict_all_freqs(data, training_lag, steps):
    """Takes a numpy matrix containing duty cycles with time in the first 
    coordinate and frequency in the second, and calculates another numpy
    matrix containing the VAR predictions with steps many new time indices
    and the same number of frequencies. We use a single model across
    frequencies (this is NOT how spec-val is implemented)."""

    columns = [str(i) for i in range(data.shape[1])]
    data = pd.DataFrame(data, columns=columns)
    model = pf.VAR(data=data, lags=training_lag)
    model.fit()
    return model.predict(h=steps)


def predict_freq_by_freq(data, training_lag, steps):
    """Takes a numpy matrix containing duty cycles with time in the first 
    coordinate and frequency in the second, and calculates another numpy
    matrix containing the VAR predictions with steps many new time indices
    and the same number of frequencies. We use separate models for each
    frequencies (this is how spec-val is implemented)."""

    output = np.zeros((steps, data.shape[1]), dtype=np.float32)

    for i in range(data.shape[1]):
        data2 = pd.DataFrame(data[:, i:i+1], columns=["x"])
        model = pf.VAR(data=data2, lags=training_lag)
        model.fit()
        result = model.predict(h=steps)
        output[:, i:i+1] = result


    return output


def predict_the_future(data, training_len, training_lag, training_rate, training_noise=1e-5):
    """Takes a numpy matrix containing duty cycles with time in the first 
    coordinate and frequency in the second, and calculates another numpy
    matrix with the same shape containing the VAR predictions. The first
    training_len many output values will be set to zero. All parameters 
    are integers and represent time steps."""

    assert 0 < training_lag < training_len and 0 < training_rate
    output = np.zeros(data.shape, dtype=np.float32)

    # add noise
    data = np.array(data, dtype=np.double, copy=True)
    data += np.random.normal(size=data.shape, scale=training_noise)

    # last reported percentage
    report = -1

    for start in range(training_len, data.shape[0], training_rate):
        steps = min(start+training_rate, data.shape[0]) - start

        output[start:start + steps] = predict_freq_by_freq(
            data[start - training_len: start, :], training_lag, steps)

        current = start / data.shape[0]
        if current - report > 0.05:
            logging.info("Training at %s", "{:.0%}".format(current))
            report = current

    return output


if __name__ == '__main__':
    data = np.zeros((20, 3))
    for i in range(data.shape[0]):
        data[i][0] = i
        data[i][1] = np.random.randint(-20, 20)
        data[i][2] = data[i][0] + data[i][1]
    pred = predict_the_future(data, 10, 1, 1, training_noise=1)
    print(data)
    print(pred)
