# Tools for ND data processing 
from bolt.spark.array import BoltArraySpark as raw_array
from bolt.spark.construct import ConstructSpark as cs
from pyqae.backend import Row, RDD
sp_array = cs.array
import numpy as np
from numpy import ndarray
from numpy import stack
import os
from skimage.io import imsave
from pyqae.utils import Optional, List

def meshgridnd_like(in_img,
                    rng_func = range):
    """
    Makes a n-d meshgrid in the shape of the input image
    >>> import numpy as np
    >>> xx, yy = meshgridnd_like(np.ones((3,2)))
    >>> xx.shape
    (3, 2)
    >>> xx
    array([[0, 0],
           [1, 1],
           [2, 2]])
    >>> xx[:,0]
    array([0, 1, 2])
    >>> yy
    array([[0, 1],
           [0, 1],
           [0, 1]])
    >>> yy[0,:]
    array([0, 1])
    >>> xx, yy, zz = meshgridnd_like(np.ones((2,3,4)))
    >>> xx.shape
    (2, 3, 4)
    >>> xx[:,0,0]
    array([0, 1])
    >>> yy[0,:,0]
    array([0, 1, 2])
    >>> zz[0,0,:]
    array([0, 1, 2, 3])
    """
    new_shape = list(in_img.shape)
    all_range = [rng_func(i_len) for i_len in new_shape]
    return tuple([x_arr.swapaxes(0,1) for x_arr in np.meshgrid(*all_range)])


def filt_tensor(image_stack, # type: ndarray
                filter_op, # type: (ndarray) -> ndarray
                tile_size=(128, 128),
                padding=(0, 0),
                *filter_args,
                **filter_kwargs):
    """
    Run an operation on a 4D tensor object (image_number, width, height, channel)

    Parameters
    ----------
    image_stack : ndarray
        a 4D distributed image
    filter_op : (ndarray) -> ndarray
        the operation to apply to 2D slices (width x height) for each channel
    tile_size : (int, int)
        the size of the tiles to cut
    padding : (int, int)
        the padding around the border
    filter_args :
        arguments to pass to the filter_op
    filter_kwargs :
        keyword arguments to pass to filter_op
    :return: a 4D tensor object of the same size
    """

    assert len(image_stack.shape) == 4, "Operations are intended for 4D inputs, {}".format(image_stack.shape)
    assert isinstance(image_stack, raw_array), "Can only be performed on BoltArray Objects"
    chunk_image = image_stack.chunk(size=tile_size, padding=padding)
    filt_img = chunk_image.map(
        lambda col_img: stack([filter_op(x, *filter_args, **filter_kwargs) for x in col_img.swapaxes(0, 2)],
                              0).swapaxes(0, 2))
    return filt_img.unchunk()


def tensor_from_rdd(in_rdd, # type: RDD
                    extract_array = lambda x: x[1], # type: (Any) -> ndarray
                    sort_func = None, # type: Optional[(Any) -> int]
                    make_idx = None # type: Optional[(Any) -> int]
                    ):
    """
    Create a tensor object from an RDD of images

    :param in_rdd: the RDD to process
    :param extract_array: the function to extract the array from the rdd (typically take the value, but some cases (ie dataframe) require more work
    :param sort_func: the function to sort by (leave none for no sorting)
    :param make_idx: the function to use to make the index otherwise just keep the sort
    :return: a distributed ND array containing the full tensor
    """
    in_rdd = in_rdd if sort_func is None else in_rdd.sortBy(sort_func)
    zip_rdd = in_rdd.zipWithIndex().map(lambda x: (x[1], extract_array(x[0]))) if make_idx is None else in_rdd.map(lambda x: (make_idx(x), extract_array(x)))
    key, val = zip_rdd.first()
    if len(val.shape)==2:
        add_channels = lambda x: np.expand_dims(x,2)
        zip_rdd = zip_rdd.mapValues(add_channels) # add channel
        val = add_channels(val)
    return fromrdd(zip_rdd, dims = val.shape, dtype = val.dtype)


def fromrdd(rdd,
            dims=None, # type: (int, int, int)
            nrecords=None, # type: Optional[int]
            dtype=None, # type: Optional[np.dtype]
            ordered=False
            ):
    """
    Load images from a RDD.
    Input RDD must be a collection of key-value pairs
    where keys are singleton tuples indexing images,
    and values are 2d or 3d ndarrays.

    Parameters
    ----------
    rdd : SparkRDD
        An RDD containing the images.
    dims : tuple or array, optional, default = None
        Image dimensions (if provided will avoid check).
    nrecords : int, optional, default = None
        Number of images (if provided will avoid check).
    dtype : string, default = None
        Data numerical type (if provided will avoid check)
    ordered : boolean, optional, default = False
        Whether or not the rdd is ordered by key
    """

    if dims is None or dtype is None:
        item = rdd.values().first()
        dtype = item.dtype
        dims = item.shape

    if nrecords is None:
        nrecords = rdd.count()

    def process_keys(record):
        k, v = record
        if isinstance(k, int):
            k = (k,)
        return k, v

    return raw_array(rdd.map(process_keys), shape=(nrecords,) + tuple(dims), dtype=dtype, split=1, ordered=ordered)



def save_tensor_local(in_bolt_array, base_path, allow_overwrite = False, file_ext = 'tif'):
    """
    Save a bolt_array on local (shared directory) paths
    :param in_bolt_array: the bolt array object
    :param base_path: the directory to save in
    :param allow_overwrite: allow overwrite to occur
    :param file_ext: the extension to save to
    """
    try:
        os.mkdir(base_path)
    except:
        print('{} already exists'.format(base_path))
        if not allow_overwrite: raise RuntimeError("Overwriting has not been enabled! Please remove directory {}".format(base_path))
    key_fix = lambda in_keys: "_".join(map(lambda k: "%05d" % (k), in_keys))

    in_bolt_array.tordd().map(lambda x: imsave(os.path.join(base_path, "{}.{}".format(key_fix(x[0]), file_ext)), x[1])).collect()
    return base_path

def tensor_to_dataframe(in_bolt_array):
    """
    Create a Spark DataFrame from a BoltArray
    :param in_bolt_array:  the input bolt array
    :return: a DataFrame with fields `position` and `array_data`
    """
    return in_bolt_array.tordd().map(lambda x: Row(position = x[0], array_data = x[1].tolist())).toDF()

def save_tensor_parquet(in_bolt_array, out_path):
    return tensor_to_dataframe(in_bolt_array).write.parquet(out_path)

def _dsum(carr, # type: np.ndarray
          cax # type: int
          ):
    # type: (np.ndarray, int) -> np.ndarray
    """
    Sums the values along all other axes but the current
    :param carr:
    :param cax:
    :return:

    >>> import numpy as np
    >>> np.random.seed(1234)
    >>> _dsum(np.zeros((3,3)), 0).astype(np.int8)
    array([0, 0, 0], dtype=int8)
    >>> _dsum(np.eye(3), 1).astype(np.int8)
    array([1, 1, 1], dtype=int8)
    >>> _dsum(np.random.randint(0, 5, size = (3,3,3)), 0).astype(np.int8)
    array([19, 17, 19], dtype=int8)
    """
    return np.sum(carr, tuple(n for n in range(carr.ndim) if n is not cax))

def get_bbox(in_vol,
             min_val = 0):
    # type: (np.ndarray, float) -> np.ndarray
    """
    Calculate a bounding box around an image in every direction
    :param in_vol: the array to look at
    :param ndim: the number of dimensions the array has
    :param min_val: the value it must be greater than to add (not equal)
    :return: a list of min,max pairs for each dimension

    >>> import numpy as np
    >>> get_bbox(np.zeros((3,3)), 0)
    [(0, 0), (0, 0)]
    >>> get_bbox(np.pad(np.eye(3).astype(np.int8), 1, mode = lambda *args: 0))
    [(1, 4), (1, 4)]
    """
    ax_slice = []
    for i in range(in_vol.ndim):
        c_dim_sum = _dsum(in_vol > min_val, i)
        wh_idx = np.where(c_dim_sum)[0]
        c_sl = sorted(wh_idx)
        if len(wh_idx) == 0:
            ax_slice += [(0, 0)]
        else:
            ax_slice += [(c_sl[0], c_sl[-1] + 1)]
    return ax_slice
def apply_bbox(in_vol, # type: np.ndarray
               bbox_list # type: List[(int,int)]
               ):
    return in_vol.__getitem__([slice(a,b,1) for (a,b) in bbox_list])


def autocrop(in_vol, # type: np.ndarray
             min_val # type: double
             ):
    # type (...) -> np.ndarray
    """
    Perform an autocrop on an image by keeping all the points above a value
    :param in_vol:
    :param min_val:
    :return:

    >>> import numpy as np
    >>> np.random.seed(1234)
    >>> autocrop(np.zeros((3,3)), 0).astype(np.bool)
    array([], shape=(0, 0), dtype=bool)
    >>> autocrop(np.eye(3), 0).astype(np.bool)
    array([[ True, False, False],
           [False,  True, False],
           [False, False,  True]], dtype=bool)
    >>> autocrop(np.random.randint(0, 10, size = (4,4)), 8).astype(np.int8)
    array([[8, 9, 1],
           [9, 6, 8],
           [5, 0, 9]], dtype=int8)
    >>> autocrop(np.pad(np.eye(3).astype(np.int8), 1, mode = lambda *args: 0),0)
    array([[1, 0, 0],
           [0, 1, 0],
           [0, 0, 1]], dtype=int8)
    """
    return apply_bbox(in_vol,get_bbox(in_vol,
                                      min_val = min_val))