import json
import tqdm
import os
import pickle
import functools
import tempfile

import cv2
import jax
import equinox as eqx
import numpy as np
import jax.numpy as jnp
import tempfile

import google.cloud.storage as gcs

class StorageHandler:
    def save(self, data, path):
        """Save the data to the specified path."""
        raise NotImplementedError("This method should be overridden.")

    def load(self, path):
        """Load the data from the specified path."""
        raise NotImplementedError("This method should be overridden.")

class GCPStorageHandler(StorageHandler):
    def __init__(self, credentials_path, bucket_name):
        self.client = gcs.Client.from_service_account_json(credentials_path)
        self.bucket = self.client.bucket(bucket_name)

    def save(self, data, path):
        """Save the data to GCP bucket at the specified path."""
        blob = self.bucket.blob(path)
        # Serialize data to bytes and upload
        serialized_data = pickle.dumps(data)
        blob.upload_from_string(serialized_data)

    def load(self, path):
        """Load the data from GCP bucket at the specified path."""
        blob = self.bucket.blob(path)
        if not blob.exists():
            raise FileNotFoundError(f"The blob '{path}' does not exist in the GCP bucket.")
        
        # Create a temporary file to download blob content
        _, temp_local_filename = tempfile.mkstemp()
        try:
            blob.download_to_filename(temp_local_filename)
            with open(temp_local_filename, 'rb') as f:
                return pickle.load(f)
        finally:
            os.unlink(temp_local_filename)  # Ensure cleanup of the temporary file

class FileStorageHandler(StorageHandler):
    def save(self, data, path):
        directory = os.path.dirname(path)
        if not os.path.exists(directory):
            os.makedirs(directory)

        with open(path, 'wb') as f:
            pickle.dump(data, f)

    def load(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"File '{path}' does not exist.")

        with open(path, 'rb') as f:
            return pickle.load(f)

def ckpt_path(ckpt_dir,iteration, ckpt_type):
    filename = f'checkpoint_{ckpt_type}_{iteration}.pkl'
    ckpt_path = os.path.join(ckpt_dir, filename)
    return ckpt_path 

def save_checkpoint(state, filepath, storage_handler):
    storage_handler.save(state, filepath)

def load_checkpoint(filepath, storage_handler):
    return storage_handler.load(filepath)

def ckpt_path(ckpt_dir, iteration, ckpt_type):
    filename = f'checkpoint_{ckpt_type}_{iteration}.pkl'
    return os.path.join(ckpt_dir, filename)

def show_samples(samples):
    for x in samples:
        y = jax.lax.clamp(0., x ,255.)
        frame = np.array(y.transpose(2,1,0),dtype=np.uint8)
        cv2.imshow('Random Frame', frame)
        cv2.waitKey(0)
    cv2.destroyAllWindows()

def load_config(config_file_path):
    try:
        with open(config_file_path, 'r') as config_file:
            config_data = json.load(config_file)
        return config_data
    except FileNotFoundError:
        raise Exception("Config file not found.")
    except json.JSONDecodeError:
        raise Exception("Error decoding JSON in the config file.")

@functools.partial(jax.jit, static_argnums=(2, 3))
def update_state(state, data, optimizer, loss_fn):
    model, opt_state, key, i = state
    new_key, subkey = jax.random.split(key)
    
    loss, grads = jax.value_and_grad(loss_fn)(model, data, subkey)

    updates, new_opt_state = optimizer.update(grads, opt_state)
    new_model = eqx.apply_updates(model, updates)
    i = i+1
    
    new_state = new_model, new_opt_state, new_key, i
    
    return loss,new_state

def tqdm_inf():
    def g():
      while True:
        yield
    return tqdm.tqdm(g())
        
def encode_frames(args, cfg):
    input_directory = args.input_dir
    output_directory = args.output_dir
    vae_checkpoint_path = args.vae_checkpoint

    def encode_frame(encoder, frame):
        frame = frame.transpose(2, 1, 0)
        encoded_frame = encoder(frame)
        return encoded_frame

    def encode_frames_batch(encoder, frames_batch):
        encoded_batch = jax.vmap(functools.partial(encode_frame, encoder))(frames_batch)
        return encoded_batch

    vae = load_checkpoint(vae_checkpoint_path)
    encoder = vae[0][0]

    video_files = [f for f in os.listdir(input_directory) if f.endswith(('.mp4', '.avi'))]

    # Create output directory if it doesn't exist
    os.makedirs(output_directory, exist_ok=True)

    for filename in video_files:
        file_base = os.path.splitext(filename)[0]
        vid_path = os.path.join(input_directory, filename)
        cap = cv2.VideoCapture(vid_path)

        # Initialize separate lists to hold original and encoded frames
        original_frames = []
        encoded_frames_1 = []
        encoded_frames_2 = []

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            original_frames.append(frame)

            if len(original_frames) == cfg["transcode"]["bs"]:
                encoded_batch_1, encoded_batch_2 = encode_frames_batch(encoder, jnp.array(original_frames))
                
                encoded_frames_1.extend(encoded_batch_1.tolist())
                encoded_frames_2.extend(encoded_batch_2.tolist())

                original_frames.clear()

        cap.release()

        # Process any remaining frames
        if original_frames:
            encoded_batch_1, encoded_batch_2 = encode_frames_batch(encoder, jnp.array(original_frames))
            
            encoded_frames_1.extend(encoded_batch_1.tolist())
            encoded_frames_2.extend(encoded_batch_2.tolist())

        # Convert lists to NumPy arrays
        encoded_frames_array_1 = np.array(encoded_frames_1)
        encoded_frames_array_2 = np.array(encoded_frames_2)

        # Aggregate into a big tuple
        latents = (encoded_frames_array_1, encoded_frames_array_2)

        output_path = os.path.join(output_directory, f"{file_base}_encoded.pkl")

        # Save using pickle
        with open(output_path, 'wb') as f:
            pickle.dump(latents, f)

