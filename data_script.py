import torchaudio
import torch
import matplotlib.pyplot as plt
from pytube import YouTube
from pydub import AudioSegment
import os
import ffmpeg
import sys
import yt_dlp
import subprocess
import pandas as pd

# combines all scripts below to take unprocessed-data.csv -> music-data.csv with paths to spectrograms and ksig
# empties unprocessed-data.csv; skips any URLs that fail
def process_data():
    # locations in directory
    ud_dir = "data/unprocessed-data.csv"
    md_dir = "data/dataset/music-data.csv"
    
    # get unprocessed data df
    ud_df = pd.read_csv(ud_dir)
    md_df = pd.read_csv(md_dir)
    processed_rows = []    # indexes of processed rows in the csv file to drop later
    index = 0   # using this to track row indices
    
    # iterating through rows with itertuples
    for row in ud_df.itertuples():
        # yt / ksig values from the row of df
        yt_url = row.URL
        ksig = row.ksig
        
        # generating .wav file from yt link
        youtube_to_wav(yt_url)
        
        # generating spectrogram from .wav file and holding onto the path
        spg_path = wav_to_spectrogram(yt_url)
        
        # check spg_path exists
        if(spg_path == None or os.path.exists(spg_path) == False):
            print(f"Failed to generate spectrogram for {yt_url}")
            continue
        
        # place information into music-data.csv if successful
        md_df.loc[len(md_df)] = [f'{spg_path}',f'{ksig}']
        
        processed_rows.append(index)
        index += 1
        
    # dropping rows we have processed
    ud_df = ud_df.drop(index=processed_rows)
    ud_df = ud_df.reset_index(drop=True)
    
    # if any data remains unprocessed this means some error occured while processing it
    # ask the user if they would like to delete or keep the unprocessed data
    unprocessed = len(ud_df)
    if(unprocessed > 0):
        inp = input(f"There is {unprocessed} unprocessed data. Would you like to delete? (y/n) ")
        if(inp == "Y" or inp == "y"):
            ud_df = ud_df.iloc[0:0]
        
    ud_df.to_csv(ud_dir, index=False, header=True)
    md_df.to_csv(md_dir, index=False, header=True)


# Helper function for youtube_to_wav
# downloads the video -> tries webm, but has mp4 as fallback
def download_video(url, output_path="."):
    try:
        yt = YouTube(url)

        # Check for .webm streams
        webm_stream = yt.streams.filter(file_extension="webm", progressive=True).first()
        if webm_stream:
            print("Downloading .webm stream...")
            webm_stream.download(output_path)
            print("Download complete: .webm format")
        else:
            print("No .webm stream found. Falling back to .mp4...")
            # Fallback to .mp4
            mp4_stream = yt.streams.filter(file_extension="mp4", progressive=True).first()
            if mp4_stream:
                mp4_stream.download(output_path)
                print("Download complete: .mp4 format")
            else:
                print("No suitable .mp4 stream found either.")
    except Exception as e:
        print(f"An error occurred: {e}")

# convert either .webm or .mp4 file to .wav
def convert_to_wav(input_file, output_dir="data/temp_data"):
    # Ensure the file exists
    if not os.path.exists(input_file):
        print(f"File not found: {input_file}")
        return

    # Get the file name without extension
    base_name = "temp"
    output_file = os.path.join(output_dir, f"{base_name}.wav")

    # Use FFmpeg to convert
    try:
        subprocess.run([
            "ffmpeg", 
            "-i", input_file, 
            "-vn",  # Exclude video (audio only)
            "-acodec", "pcm_s16le",  # WAV codec
            "-ar", "44100",  # Audio sample rate
            "-ac", "2",  # Number of audio channels
            output_file
        ], check=True)
        print(f"Conversion successful: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred during conversion: {e}")


# testing the above functions



# takes a youtube url and creates a .wav audio file in a temp directory
def youtube_to_wav(video_url, output_path="data/temp_data/temp.wav"):
    try:
        # Download the audio using yt-dlp (output as .m4a or .webm)
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'downloaded_audio.%(ext)s',  # Temporary file name
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Downloading audio from: {video_url}")
            ydl.download([video_url])

        # Load the downloaded audio with pydub (change extension based on what yt-dlp downloaded)
        audio = AudioSegment.from_file('downloaded_audio.webm')  # Adjust extension if needed

        # Export as .wav
        audio.export(output_path, format="wav")

        print(f"Audio successfully saved as {output_path}")

        # Cleanup downloaded audio
        os.remove("downloaded_audio.webm")

    except Exception as e:
        print(f"An error occurred: {e}")

youtube_to_wav("https://www.youtube.com/watch?v=QoEH4umX2y8")

# Load temp audio -> saves it to spectrograms data and returns path directory to spectrogram
def wav_to_spectrogram(file_name):
    # audio path for temp wav file
    audio_path = r"data/temp_data/temp.wav"
    
    # checking the path exists; fails if it doesn't
    if(os.path.exists(audio_path) == False):
        return None
    
    # loading waveform and sample rate from audio
    waveform, sample_rate = torchaudio.load(audio_path)

    # Create the MelSpectrogram transform
    mel_spectrogram_transform = torchaudio.transforms.MelSpectrogram(
        sample_rate=sample_rate,
        
            # number of mel bands
        n_mels=64,
        
            # defines the frequency range of interest
        f_min=125,
        f_max=7500,
        
            # n_fft = number of samples per segment
            # a larger value gives better frequency resolution but worse time resolution
        n_fft=1024,      
        
            # defines the number of samples between successive windows
            # reducing it increases resolution but also increases computation cost
            # generally 1/4 x n_fft
        hop_length=256
    )

    # Apply the transform
    mel_spectrogram = mel_spectrogram_transform(waveform)

    # Convert to decibels (log scale)
    log_mel_spectrogram = torchaudio.transforms.AmplitudeToDB()(mel_spectrogram)
    spectrogram = log_mel_spectrogram[0]        # (num of mel bins, num of channels)

    # Creating name for new spectrogram
    df = pd.read_csv("data/dataset/music-data.csv")
    index = len(df)
    
    # Define the output path
    output_dir = "data/dataset/spectrograms"
    output_name = f"sp_{index}.png"
    os.makedirs(output_dir, exist_ok=True)
    output_str = f"{output_dir}/{output_name}"      # need this string to return
    output_path = os.path.join(output_dir, output_name)

    # Save the spectrogram as an image
    plt.figure(figsize=(10, 4))  # Adjust the size for consistent image dimensions
    plt.imshow(spectrogram.squeeze().numpy(), origin="lower", aspect="auto", cmap="viridis")
    plt.axis("off")  # Remove axes for a clean image
    plt.tight_layout(pad=0)
    plt.savefig(output_path, dpi=300, bbox_inches="tight", pad_inches=0)
    plt.close()  # Close the figure to free memory

    print(f"Spectrogram saved as an image at {output_path}")

    # Cleanup temp_data audio
    os.remove("data/temp_data/temp.wav")
    
    # return output path to store in csv
    return output_str


# # Plot the Mel spectrogram
# plt.figure(figsize=(10, 6))
# plt.imshow(log_mel_spectrogram[0].numpy(), aspect='auto', origin='lower', cmap='inferno')
# plt.title('Mel Spectrogram')
# plt.ylabel('Mel bins')
# plt.xlabel('Time')
# plt.colorbar(format="%+2.0f dB")
# plt.show()


        ## ESTIMATING KEY SIGNATURE WITH ESSENTIA (~80% ACCURATE)
# import librosa
# from essentia.standard import KeyExtractor

# # Load audio with librosa
# audio_path = "data/genres_original/blues/blues.00000.wav"
# y, sr = librosa.load(audio_path, sr=None)

# # Extract the key using Essentia
# key_extractor = KeyExtractor()
# key, scale, strength = key_extractor(y)

# print(f"Estimated Key: {key}")
# print(f"Scale: {scale}")
# print(f"Strength: {strength}")