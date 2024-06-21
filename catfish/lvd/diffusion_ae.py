import os
import collections

import jax

import optax

import catfish.lvd.models.dist_autoencoding_diffusion as daed
import catfish.lvd.models.dist_utils as du
import catfish.lvd.gcp_data_loader as dl
import catfish.lvd.diffusion_core as dc


DAEModel = collections.namedtuple(["encoder", "decoder"])

class DiffAEHarness:
    """Sharded Diffusion autoencoder harness"""

    def __init__(self, args, cfg):
        self.args = args
        self.cfg = cfg
        self.state = {}
        self.optimizer = None
        self.prng_key = None
        self.dist_manager = None
        self.data_loader = None
        self.credentials_path = None
        self.gcs_bucket = None

        self.parse_args()
        self.init_dist_manager()
        self.init_data_loader()
        self.make_model()
    
    def parse_args(self):
        self.credentials_path = self.args.gcs_json
        self.gcs_bucket = self.args.gcs_bucket
        self.ckpt_path = self.args.ckpt_path
        self.log_file = self.args.ckpt_path

    def init_data_loader(self):
        #Only init dataloader on first node 
        #TODO:Shard dataloader
        resolution = self.cfg["diffuison_auto_encoder"]

        if self.dist_manager.pid == 0:
            self.gcp_data_loader = dl.VideoDataLoader(
                self.credentials_path,
                self.args.gcs_bucket,
                self.args.latent_folder,
                target_resolution=resolution,
                pkl_folder_path=self.args.video_folder
            )
        else:
            self.gcp_data_loader = None
    
    def init_dist_manager(self):
        dm_cfg = self.cfg["dist_manager"]

        mesh_shape = dm_cfg["mesh_shape"]

        self.dist_manager = du.DistManager(mesh_shape, self.credientials_path)
    
    def make_model(self):
        model_conf = self.conf["diffusion_auto_encoder"]["model"]
        enc_conf = model_conf["encoder"]
        dec_conf = model_conf["decoder"]
        
        self.state["prng_key"], enc_key, dec_key = jax.random.split(self.state["prng_key"],3)

        self.state["model"] = DAEModel(
            encoder=daed.Encoder(
                self.dist_manager, 
                key=enc_key, 
                k =enc_conf["k"],
                n_layers=enc_conf["n_layers"]
            ),
            decoder=daed.Decoder(
                self.dist_manager, 
                key=dec_key, 
                k =dec_conf["k"],
                n_layers=dec_conf["n_layers"]
            )
        )
    
    def make_optimizer(self):
        opt_cfg = self.cfg["diffusion_auto_encoder"]["train"]
        
        self.optimizer = optax.adam(lr=opt_cfg["lr"])
        self.state["opt_state"] = self.optimizer.init(self.model)
    
    def save_checkpoint(self, path):
        model_path = os.path.join(path, "model")
        model_encoder_path = os.path.join(model_path, "encoder")
        self.model.encoder.save(model_encoder_path)
        model_decoder_path = os.path.join(model_path, "encoder")
        self.model.decoder.save(model_decoder_path)

        opt_path = os.path.join(path, "opt_state")
        for key, value in self.opt_state:
            if hasattr(value, "save"):
                opt_state_encoder_path = os.path.join(
                    opt_path, key, "encoder")
                value.encoder.save(opt_state_encoder_path)
                opt_state_decoder_path = os.path.join(
                    opt_path, key, "encoder")
                value.encoder.save(opt_state_decoder_path)
            else:
               #TODO fix backend 
               pass
    
    def _new_ckpt_path(self):
        pass
    
    def _latest_ckpt_path(self):
        pass
    
    def load_checkpoint(self, path):
        model_path = os.path.join(path, "model")
        model_encoder_path = os.path.join(model_path, "encoder")
        self.model.encoder.save(model_encoder_path)
        model_decoder_path = os.path.join(model_path, "encoder")
        self.model.decoder.save(model_decoder_path)

        opt_path = os.path.join(path, "opt_state")
        for key, value in self.opt_state:
            if hasattr(value, "save"):
                opt_state_encoder_path = os.path.join(
                    opt_path, key, "encoder")
                value.encoder.save(opt_state_encoder_path)
                opt_state_decoder_path = os.path.join(
                    opt_path, key, "encoder")
                value.encoder.save(opt_state_decoder_path)
            else:
               #TODO fix backend 
               pass
    
    def most_recent_ckpt(self):
        pass

    def new_ckpt_path(self, id):
        ckpt_n = self.most_recent_ckpt()

        ckpt_freq = self.cfg["diffusion_autoencoder"]["train"]["ckpt_freq"]
        
        new_ckpt_n = ckpt_n + ckpt_freq
        assert id == new_ckpt_n

        os.path.join(self.args.ckpt_path,"ckpt_path")
    
    def latest_ckpt_path(self):
        #TODO:
        pass
    
    def train(self):
        args = self.args
        cfg = self.cfg

        ckpt_freq = self.cfg["diffusion_autoencoder"]["train"]["ckpt_freq"]

        state = (self.model, self.opt_state, self.prng_key)

        def loss_fn(model, data, subkey):
            latent = model.encoder(data)
            diffusion_data = (latent, data)
            loss = dc.diffusion_loss(
                model.decoder, diffusion_data, dc.f_neg_gamma, subkey)
            return loss
        
        checkpoint = args.ckpt
        if checkpoint is None:
            state = (self.model, self.opt_state, self.prng_key)
        else:
            load_checkpoint
        
        for data in self.data_loader:
            loss, state = dc.update(state, data, self.optimizer, loss_fn)
            print(loss)

    def autoencode(self):
        args = self.args
        cfg = self.cfg

        latest_ckpt_path = self.latest_ckpt_path()
        self.load_checkpoint(latest_ckpt_path)

    


