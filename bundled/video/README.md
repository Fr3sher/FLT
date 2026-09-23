# Video lane

Create a video training set directly from **Datasets → New dataset → Video**. Choose its model, clip length and size, then add local files in **Add videos**. The optional web source panel can send selected videos to the same import endpoint. Imports report progress and skips, can be stopped, and avoid duplicating an already imported clip.

Video Bank also turns rushes into shots for review, captioning and dataset creation. Training sets include local training, checkpoint history and identity-reference support. The H3 Test Studio generates image- or text-to-video clips, compares LoRAs, continues clips manually and interpolates frames.

Preparation installs CPU video decoding and encoding tools. Direct imports accept the selected videos, with 200 MB per file and 1 GB per upload; splitting keeps up to eight full clips per source. Files too short for the requested frame count are skipped. The first source can set the dataset size, fitted to the model; subsequent imports use that size. Add captions before training.
