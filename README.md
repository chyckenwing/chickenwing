# Chickenwing

Chickenwing is a terminal-first YouTube downloader built on `yt-dlp`.

It gives you:

- a global `chickenwing` command
- direct link downloads with sane defaults
- search-based downloads with top 5 results
- `audio <query-or-link>` for MP3 mode
- a dedicated `Chickenwing Downloads` folder in your Windows Downloads directory

## Install

### Local repo

```powershell
pip install .
```

### Recommended global install

```powershell
pipx install .
```

### From GitHub

```powershell
pipx install git+https://github.com/chyckenwing/chickenwing.git
```

If `pipx` is not installed yet:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

## Run

```powershell
chickenwing
```

Funny alias:

```powershell
wingit
```

Module form also works:

```powershell
py -m chickenwing
```

## Usage

- Paste a YouTube link to download the best video immediately.
- Type search words to pick from the top 5 results.
- Prefix with `audio ` to download MP3.
- Type `settings` if you want to change runtime behavior.
- Type `quit` or press `Enter` on an empty prompt to exit.

## Download location

Chickenwing saves everything here:

```text
%USERPROFILE%\Downloads\Chickenwing Downloads
```

Inside that folder it keeps:

- `videos`
- `audio`
- `download_archive.txt`

## ffmpeg

For best audio extraction and video merging results, make sure `ffmpeg` is installed and available on `PATH`.
