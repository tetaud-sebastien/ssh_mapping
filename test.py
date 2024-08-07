import torch
import xarray as xr
import numpy as np
from loguru import logger
from torch.utils.data.dataloader import DataLoader
from tqdm import tqdm
from datasets import TestDataset, TestDataset3D
import os
from models import AutoencoderCNN
from train_logs import log_prediction_plot
from utils import count_model_parameters
import yaml
import diags
from utils import load_model
from loguru import logger

def prediction(test_dataloader, device, model, ymin, ymax):

    list_pred = []

    for data in tqdm(test_dataloader, ncols=100, colour='#FF33EC'):

        inputs, _ = data
        inputs = inputs.to(device, dtype=torch.float)

        with torch.no_grad():
            pred = model(inputs)

        pred = pred[:, :, 3, :, :]
        pred = torch.squeeze(pred, 0)
        pred = pred.detach().cpu().numpy()[0,:,:]
        # Back to real values before normalization
        # We should create a specific function for normalization and associated de-normalization
        pred = (pred - 0.01) * (ymax - ymin) + ymin

        # Append to list
        list_pred.append(pred)

    return np.asarray(list_pred)

# Function to create 3D datasets with a depth of 10 days
def create_3d_datasets(ds_inputs, ds_target, depth=6):
    data_inputs = ds_inputs.values
    data_target = ds_target.values

    new_inputs = []
    new_target = []

    for i in range(0, len(data_inputs)):

        if i < (depth/2):

            input_slice = data_inputs[0: depth, :, :]

        elif i > (depth/2) and i < (len(data_inputs)- (depth/2)):

            input_slice = data_inputs[i - (int(depth/2)): i + (int(depth/2)), :, :]

        else:

            input_slice = data_inputs[- depth:, :, :]



        target_slice = data_target[i, :, :]
        new_inputs.append(input_slice)
        new_target.append(target_slice)

    new_inputs = np.array(new_inputs)
    new_target = np.array(new_target)

    return new_inputs, new_target


def test(config_file, checkpoint_path, prediction_dir):

    model_architecture = config_file["model_architecture"]
    test_start = config_file["test_start"]
    test_end = config_file["test_end"]
    inputs_path = config_file["inputs_path"]
    target_path = config_file["target_path"]
    name_var_inputs = config_file["name_var_inputs"]
    name_var_target = config_file["name_var_target"]
    name_diag = config_file['name_diag']
    write_netcdf = config_file['write_netcdf']
    animate = config_file['animate']
    compute_metrics = config_file['compute_metrics']

    test_dir = os.path.join(prediction_dir,"test_inference")
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)

    model, device = load_model(checkpoint_path, model_architecture, device='cuda', model_eval=True)


    nb_parameters = count_model_parameters(model=model)
    logger.info(f"Model is on Cuda: {next(model.parameters()).is_cuda}")
    logger.info("Number of parameters {}: ".format(nb_parameters))

    ds_inputs = xr.open_dataset(inputs_path)
    ds_target = xr.open_dataset(target_path)

    ds_inputs = ds_inputs.sel(time=slice(test_start, test_end))[name_var_inputs]
    ds_target = ds_target.sel(time=slice(test_start, test_end))[name_var_target]

    test_inputs_3d, test_target_3d = create_3d_datasets(ds_inputs, ds_target, depth=6)

    test_dataset = TestDataset3D(test_inputs_3d, test_target_3d)
    test_dataloader = DataLoader(test_dataset, batch_size=1, shuffle=False)
    # Run prediction and stack in an array
    pred = prediction(test_dataloader, device, model, ds_target.min().values, ds_target.max().values)

    # Create dataset
    ds_pred = ds_target.copy()
    ds_pred.data = pred

    if write_netcdf:
        ds_pred.to_netcdf(f'{test_dir}/pred.nc')

    # Run diagnostics
    diag = getattr(diags, name_diag)(ds_inputs, ds_pred, ds_target, test_dir)
    if animate:
        logger.info('Diagnostics: animate')
        diag.animate()
    if compute_metrics:
        logger.info('Diagnostics: compute_metrics')
        diag.compute_metrics()
        diag.Leaderboard()

# if __name__ == '__main__':

#     with open("config.yaml", "r") as stream:
#         try:
#             config = yaml.safe_load(stream)
#         except yaml.YAMLError as exc:
#             logger.info(exc)

#     test(config, 'training_inference/2024_07_12_15_39_47/best.pth', 'training_inference/2024_07_12_15_39_47/')

