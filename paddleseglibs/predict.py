# Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import contextlib
import os

import paddle

from paddleseglibs.paddleseg.cvlibs import manager, Config
from paddleseglibs.paddleseg.utils import get_sys_env, logger, config_check, get_image_list
from paddleseglibs.paddleseg.utils.utils import load_entire_model
from paddleseglibs.paddleseg.core import predict

import time


# Anchor default paths to the paddleseglibs/ package itself so they are
# independent of caller cwd. Without this, any caller outside repo root
# (e.g. experiments/, notebooks/) hits FileNotFoundError.
_PKG_ROOT = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_PKG_ROOT)
DEFAULT_CONFIG_PATH = os.path.join(
    _PKG_ROOT, 'configs', 'segformer', 'segformer_b5_diaphragm_excursion.yml')
DEFAULT_MODEL_PATH = os.path.join(
    _PKG_ROOT, 'output', 'model', 'diaphragm_excursion_3x', 'best_model', 'model.pdparams')
DEFAULT_SAVE_DIR = os.path.join(_PKG_ROOT, 'output', 'prediction')


@contextlib.contextmanager
def _chdir(target):
    """Context manager that temporarily chdir to `target`, restores on exit.

    Needed because paddleseglibs/configs/_base_/*.yml hard-codes cwd-relative
    paths (dataset_root, val_path). paddleseg's Dataset eagerly validates
    these on Config(...).val_dataset, so we must guarantee cwd == repo root
    during config load no matter where the caller invoked Python from.
    """
    prev = os.getcwd()
    try:
        os.chdir(target)
        yield
    finally:
        os.chdir(prev)


def parse_args():
    parser = argparse.ArgumentParser(description='Model prediction')

    # params of prediction
    parser.add_argument(
        "--config",
        dest="cfg",
        help="The config file.",
        default=DEFAULT_CONFIG_PATH, type=str)
    # thickness 'configs/segformer/segformer_b5_cityscapes_1024x1024_160k_diaphragm2.yml'

    parser.add_argument(
        '--model_path',
        dest='model_path',
        help='The path of model for prediction',
        type=str,
        default=DEFAULT_MODEL_PATH)
    parser.add_argument(
        '--image_path',
        dest='image_path',
        help=
        'The path of image, it can be a file or a directory including images',
        type=str,
        default='')

    parser.add_argument(
        '--save_dir',
        dest='save_dir',
        help='The directory for saving the predicted results',
        type=str,
        default=DEFAULT_SAVE_DIR)

    # augment for prediction
    parser.add_argument(
        '--aug_pred',
        dest='aug_pred',
        help='Whether to use mulit-scales and flip augment for prediction',
        action='store_true')
    parser.add_argument(
        '--scales',
        dest='scales',
        nargs='+',
        help='Scales for augment',
        type=float,
        default=1.0)
    parser.add_argument(
        '--flip_horizontal',
        dest='flip_horizontal',
        help='Whether to use flip horizontally augment',
        action='store_true')
    parser.add_argument(
        '--flip_vertical',
        dest='flip_vertical',
        help='Whether to use flip vertically augment',
        action='store_true')

    # sliding window prediction
    parser.add_argument(
        '--is_slide',
        dest='is_slide',
        help='Whether to prediction by sliding window',
        action='store_true')
    parser.add_argument(
        '--crop_size',
        dest='crop_size',
        nargs=2,
        help=
        'The crop size of sliding window, the first is width and the second is height.',
        type=int,
        default=None)
    parser.add_argument(
        '--stride',
        dest='stride',
        nargs=2,
        help=
        'The stride of sliding window, the first is width and the second is height.',
        type=int,
        default=None)

    # custom color map
    parser.add_argument(
        '--custom_color',
        dest='custom_color',
        nargs='+',
        help=
        'Save images with a custom color map. Default: None, use paddleseg\'s default color map.',
        type=int,
        default=None)

    # custom image resize ratio
    parser.add_argument(
        '--resize',
        dest='resize',
        help=
        'image resize ratio',
        type=float,
        default=1.0)
    return parser.parse_args()


def get_test_config(cfg, args):
    test_config = cfg.test_config
    if args.aug_pred:
        test_config['aug_pred'] = args.aug_pred
        test_config['scales'] = args.scales

    if args.flip_horizontal:
        test_config['flip_horizontal'] = args.flip_horizontal

    if args.flip_vertical:
        test_config['flip_vertical'] = args.flip_vertical

    if args.is_slide:
        test_config['is_slide'] = args.is_slide
        test_config['crop_size'] = args.crop_size
        test_config['stride'] = args.stride

    if args.custom_color:
        test_config['custom_color'] = args.custom_color

    return test_config


def build_predictor(
        config_path=DEFAULT_CONFIG_PATH,
        model_path=DEFAULT_MODEL_PATH,
        device=None,
        save_dir=DEFAULT_SAVE_DIR,
        resize_ratio=1.0,
        aug_pred=False,
        scales=1.0,
        flip_horizontal=False,
        flip_vertical=False,
        is_slide=False,
        stride=None,
        crop_size=None,
        custom_color=None,
        save_predictions=True):
    """
    一次性建立 predictor context：解析 config、建立 model、載入權重。
    回傳的 dict 之後丟給 predict_one() 重複使用，weights 不會重 load。

    Args:
        config_path: YAML config 路徑
        model_path: .pdparams 權重檔
        device: 'gpu' / 'cpu' / None（None 時自動偵測）
        其他參數對應原 argparse 旗標，預設值與舊 CLI 預設一致
    """
    start = time.time()

    if device is None:
        env_info = get_sys_env()
        device = 'gpu' if env_info['Paddle compiled with cuda'] and env_info[
            'GPUs used'] else 'cpu'
    paddle.set_device(device)

    if not config_path:
        raise RuntimeError('No configuration file specified.')

    # cwd-anchor: paddleseg YAML 內的 dataset_root / val_path 都是 cwd-relative
    with _chdir(_REPO_ROOT):
        cfg = Config(config_path)
        val_dataset = cfg.val_dataset
        if not val_dataset:
            raise RuntimeError(
                'The verification dataset is not specified in the configuration file.'
            )

        msg = '\n---------------Config Information---------------\n'
        msg += str(cfg)
        msg += '------------------------------------------------'
        logger.info(msg)

        model = cfg.model
        transforms = val_dataset.transforms

        test_config = cfg.test_config
        if aug_pred:
            test_config['aug_pred'] = aug_pred
            test_config['scales'] = scales
        if flip_horizontal:
            test_config['flip_horizontal'] = flip_horizontal
        if flip_vertical:
            test_config['flip_vertical'] = flip_vertical
        if is_slide:
            test_config['is_slide'] = is_slide
            test_config['crop_size'] = crop_size
            test_config['stride'] = stride
        if custom_color:
            test_config['custom_color'] = custom_color

        config_check(cfg, val_dataset=val_dataset)

        load_start = time.time()
        load_entire_model(model, model_path)
        logger.info("Load model cost: {:.2f}s".format(time.time() - load_start))

    logger.info("build_predictor total cost: {:.2f}s".format(time.time() - start))

    return {
        'model': model,
        'transforms': transforms,
        'model_path': model_path,
        'save_dir': save_dir,
        'save_predictions': save_predictions,
        'resize_ratio': resize_ratio,
        'test_config': test_config,
    }


def predict_one(predictor, image_path, dcm_array=None, image_dir=None):
    """
    用已建好的 predictor 跑單張影像。model weights 不重新 load。

    Returns:
        PIL.Image.Image：pseudo-color mask，mode='P'（與舊 infer() 回傳型別一致）
    """
    return predict(
        predictor['model'],
        pixel_array=dcm_array,
        model_path=predictor['model_path'],
        transforms=predictor['transforms'],
        image_list=[image_path],
        image_dir=image_dir,
        save_dir=predictor['save_dir'],
        resize_ratio=predictor['resize_ratio'],
        skip_model_load=True,
        save_predictions=predictor['save_predictions'],
        **predictor['test_config'])


def infer(image_list, image_dir, dcm_array=None, model_path=None):
    """
    向後相容入口。內部改用 build_predictor() + predict_one()，
    但對外行為（回傳值、副作用）與舊版一致。

    NOTE: 仍呼叫 parse_args() 以保留 CLI 預設值來源。新程式請改用
    build_predictor() + predict_one()，避免 sys.argv 耦合。
    """
    total_start = time.time()

    args = parse_args()
    if model_path is not None:
        args.model_path = model_path

    predictor = build_predictor(
        config_path=args.cfg,
        model_path=args.model_path,
        save_dir=args.save_dir,
        resize_ratio=args.resize,
        aug_pred=args.aug_pred,
        scales=args.scales,
        flip_horizontal=args.flip_horizontal,
        flip_vertical=args.flip_vertical,
        is_slide=args.is_slide,
        stride=args.stride,
        crop_size=args.crop_size,
        custom_color=args.custom_color,
    )

    logger.info('Number of predict images = {}'.format(len(image_list)))

    pred_mask = None
    for im_path in image_list:
        pred_mask = predict_one(
            predictor, im_path, dcm_array=dcm_array, image_dir=image_dir)

    logger.info("Total cost: {:.2f}s".format(time.time() - total_start))
    return pred_mask



