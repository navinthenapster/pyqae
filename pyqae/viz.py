"""
Package for visualization tools and support
"""
import base64
from io import BytesIO
from itertools import chain
from warnings import warn

import numpy as np
from PIL import Image as PImage
from matplotlib import animation, rc
from matplotlib.pyplot import cm

from pyqae.utils import get_temp_filename, Tuple, Optional

fake_HTML = lambda x: x  # dummy function
try:
    from IPython.display import HTML
except ImportError:
    HTML = fake_HTML


def _np_to_uri(in_array,  # type: np.ndarray
               cmap='RdBu'):
    """
    Convert a numpy array to a data URI with a png inside

    >>> _np_to_uri(np.zeros((100,100)))
    'iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAABUElEQVR4nO3SQQEAEADAQBQRT/8ExPDYXYI9Ns/Yd5C1fgfwlwHiDBBngDgDxBkgzgBxBogzQJwB4gwQZ4A4A8QZIM4AcQaIM0CcAeIMEGeAOAPEGSDOAHEGiDNAnAHiDBBngDgDxBkgzgBxBogzQJwB4gwQZ4A4A8QZIM4AcQaIM0CcAeIMEGeAOAPEGSDOAHEGiDNAnAHiDBBngDgDxBkgzgBxBogzQJwB4gwQZ4A4A8QZIM4AcQaIM0CcAeIMEGeAOAPEGSDOAHEGiDNAnAHiDBBngDgDxBkgzgBxBogzQJwB4gwQZ4A4A8QZIM4AcQaIM0CcAeIMEGeAOAPEGSDOAHEGiDNAnAHiDBBngDgDxBkgzgBxBogzQJwB4gwQZ4A4A8QZIM4AcQaIM0CcAeIMEGeAOAPEGSDOAHEGiDNAnAHiDBBngDgDxBkgzgBxDxypAoX8C2RlAAAAAElFTkSuQmCC'
    """
    test_img_data = np.array(in_array).astype(np.float32)
    test_img_data -= test_img_data.mean()
    test_img_data /= test_img_data.std()
    test_img_color = cm.get_cmap(cmap)((test_img_data + 0.5).clip(0, 1))
    test_img_color *= 255
    p_data = PImage.fromarray(test_img_color.clip(0, 255).astype(np.uint8))
    rs_p_data = p_data.resize((128, 128), resample=PImage.BICUBIC)
    out_img_data = BytesIO()
    rs_p_data.save(out_img_data, format='png')
    out_img_data.seek(0)  # rewind
    return base64.b64encode(out_img_data.read()).decode("ascii").replace("\n",
                                                                         "")


_wrap_uri = lambda data_uri: "data:image/png;base64,{0}".format(data_uri)


# noinspection PyShadowingNames
def display_uri(uri_list, wrap_ipython=True):
    """

    show_uri(_np_to_uri(np.zeros((100,100))))

    """

    html_func = HTML if wrap_ipython else fake_HTML
    out_html = ""
    for in_uri in uri_list:
        out_html += """<img src="{0}" width = "100px" height = "100px" />""".format(
            _wrap_uri(in_uri))
    return html_func(out_html)


try:
    from skimage.measure import marching_cubes_classic
except ImportError:
    warn("pyqae works best with the latest version of skimage")
    from skimage.measure import marching_cubes as marching_cubes_classic
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from mpl_toolkits.mplot3d.axes3d import Axes3D
import matplotlib.pyplot as plt

MAX_COMP_LIMIT = 50


def draw_3d_labels(in_bone_labels,  # type: np.ndarray
                   start_idx=1,  # type: int
                   rescale_func=None,
                   vox_size=None,
                   verbose=False,
                   level=0,
                   figsize=(10, 12),
                   force_shape=True,
                   flip=True):
    # type: (...) -> Tuple[Axes3D, matplotlib.figure.Figure]
    # somehow add type to rescale_fun Optional[Function(np.ndarray, np.ndarray)]

    """

    :param in_bone_labels:
    :param start_idx:
    :param rescale_func: a function to downscale the images (if needed)
    :return:
    >>> test_labels = np.stack([np.eye(3),2*np.eye(3)]).astype(int); tvx = np.array([0.1, 3.0, 0.33])
    >>> ax, fig = draw_3d_labels(test_labels, verbose = True)
    Adding meshes 1, sized 3.0
    Adding meshes 2, sized 3.0
    >>> type(ax)
    <class 'matplotlib.axes._subplots.Axes3DSubplot'>
    >>> type(fig)
    <class 'matplotlib.figure.Figure'>
    """
    # todo I don't think the Function typing is correct

    # plt.rcParams['savefig.bbox'] = 'tight'
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, projection='3d')
    # Fancy indexing: `verts[faces]` to generate a collection of triangles
    cmap = plt.cm.get_cmap('nipy_spectral_r')
    max_comp = in_bone_labels.max()

    rescale_func = rescale_func if rescale_func is not None else lambda x: x
    if flip:
        ax_flip = lambda x: rescale_func(x)[::-1].swapaxes(0, 2).swapaxes(0, 1)
    else:
        ax_flip = lambda x: rescale_func(x)

    for i in range(start_idx, min(max_comp, MAX_COMP_LIMIT) + 1):

        if i == 0:
            v_img = ax_flip((in_bone_labels > 0).astype(np.float32))
        else:
            v_img = ax_flip((in_bone_labels == i).astype(np.float32))

        if verbose:
            print('Adding meshes {}, sized {}'.format(i, np.sum(v_img)))
        mc_args = {'level': level}

        if vox_size is not None:
            mc_args['spacing'] = vox_size

        verts, faces = marching_cubes_classic(v_img, **mc_args)

        mesh = Poly3DCollection(verts[faces])

        if i > 0:
            mesh.set_facecolor(cmap(i / max_comp)[:3])
            mesh.set_alpha(0.75)
        else:
            mesh.set_facecolor([1, 1, 1])
            mesh.set_edgecolor([0, 0, 0])
            mesh.set_alpha(0.1)
        # mesh.set_edgecolor(cmap(i/max_comp)[:3])

        ax.add_collection3d(mesh)
    n_shape = ax_flip(in_bone_labels).shape
    if force_shape:
        ax.set_xlim(0, n_shape[0])
        ax.set_ylim(0, n_shape[1])
        ax.set_zlim(0, n_shape[2])
    else:
        pass  # ax.set_aspect('equal')
    ax.view_init(45, 45)
    ax.axis('off')
    return ax, fig


def _checkffmpeg():
    try:
        plt.rcParams['animation.ffmpeg_path']
    except KeyError as ke:
        raise ValueError(
            "ffmpeg path is not specified, it probably needs to be installed using the default package manager: brew install ffmpeg",
            ke)


def make_3d_animation(in_fig,  # type: plt.Figure
                      in_ax,  # type: Axes3D
                      frames,  # type: int
                      fps=1,
                      file_path=None,  # type: Optional[str]
                      as_html=True
                      ):
    _checkffmpeg()
    frame_arr = np.linspace(0, 180, frames)

    def _updatefig(ind):
        in_ax.view_init(45, frame_arr[ind])
        return in_ax

    ani = animation.FuncAnimation(in_fig, _updatefig, frames=frames)

    if file_path is None:
        file_path = get_temp_filename('.gif')

    ani.save(file_path, fps=fps, writer='imagemagick')
    rc('animation', html='html5')
    if as_html:
        return HTML(ani.to_html5_video())
    else:
        return ani


def make_stack_animation(in_stack,  # type: np.ndarray
                         frames,  # type: int
                         fps=1,
                         file_path=None,  # type: Optional[str]
                         as_html=True,
                         bounce=False,
                         fig_size=(4, 4),
                         fig_dpi=300,
                         **plt_kwargs
                         ):
    assert len(
        in_stack.shape) == 3, "Only 3D arrays are supported for the stack animation code"
    _checkffmpeg()
    in_fig, in_ax = plt.subplots(1, 1, figsize=fig_size, dpi=fig_dpi)
    _img_ax = in_ax.imshow(in_stack[0], **plt_kwargs)
    in_ax.axis('off')
    frame_arr = np.linspace(0, in_stack.shape[0] - 1,
                            frames / 2 if bounce else frames)  # type: np.ndarray
    if bounce:
        frame_arr = np.array(
            list(frame_arr.tolist()) + list(reversed(frame_arr)))

    def _updatefig(ind):
        _img_ax.set_array(in_stack[int(frame_arr[ind])])
        return _img_ax

    ani = animation.FuncAnimation(in_fig, _updatefig, frames=frames)

    if file_path is None:
        file_path = get_temp_filename('.gif')

    ani.save(file_path, fps=fps, writer='imagemagick')
    rc('animation', html='html5')
    if as_html:
        ani_link = ani.to_html5_video()
        in_fig.clf()
        plt.close('all')
        return HTML(ani_link)
    else:
        return ani


def draw_3d_label_animation(in_bone_labels,
                            frames=18,
                            fps=1,
                            start_idx=1,
                            rescale_func=None,
                            file_path=None,
                            as_html=True):
    _checkffmpeg()
    ax, fig = draw_3d_labels(in_bone_labels=in_bone_labels,
                             rescale_func=rescale_func,
                             start_idx=start_idx)
    out_la = make_3d_animation(in_fig=fig, in_ax=ax, frames=frames, fps=fps,
                               file_path=file_path, as_html=as_html)
    if as_html:  # only close the figures if we are only keeping the html
        fig.clf()
        plt.close('all')
    return out_la


def label_score(gt_labels, sp_segs):
    """

    :param gt_labels:
    :param sp_segs:
    :return:
    """


def _create_tf_graph():
    import tensorflow as tf
    from pyqae.dnn.layers import add_com_grid_3d_tf
    with tf.Graph().as_default() as g:
        in_val = tf.placeholder(dtype=tf.float32, shape=(9, 4, 3, 2, 1))
        out_val = add_com_grid_3d_tf(in_val, False)
    return g


def tf_graph_to_dot(in_graph, add_nodes=True, add_edges=True):
    # type: (tf.Graph, bool, bool) -> pydot.Dot
    """
    Great a graph from a tensorflow graph to dot
    :param in_graph:
    :param add_nodes:
    :param add_edges:
    :return:
    >>> c_dot = tf_graph_to_dot(_create_tf_graph())
    Number of nodes: 128
    Number of edges: 162
    >>> print(c_dot.to_string()[:60])
    digraph G {
    rankdir=UD;
    concentrate=True;
    node [shape=record
    """
    import pydot
    dot = pydot.Dot()
    dot.set('rankdir', 'UD')
    dot.set('concentrate', True)
    dot.set_node_defaults(shape='record')
    all_ops = in_graph.get_operations()
    all_tens_dict = {k: i for i, k in enumerate(
        set(chain(*[c_op.outputs for c_op in all_ops])))}
    print('Number of nodes:', len(all_tens_dict.keys()))
    if add_nodes:
        for c_node in all_tens_dict.keys():
            node = pydot.Node(c_node.name)  # , label=label)
            dot.add_node(node)
    if add_edges:
        edge_count = 0
        for c_op in all_ops:
            for c_output in c_op.outputs:
                for c_input in c_op.inputs:
                    dot.add_edge(pydot.Edge(c_input.name, c_output.name))
                    edge_count += 1
        print('Number of edges:', edge_count)
    return dot


if __name__ == '__main__':
    import doctest
    # noinspection PyUnresolvedReferences
    import pyqae.viz

    doctest.testmod(pyqae.viz, verbose=True,
                    optionflags=doctest.ELLIPSIS)
