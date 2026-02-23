# Station Audio Toolkit

A Pure Data (Pd) interactive audio toolkit for producing broadcast-quality audio elements — jingles, sweepers, stingers, bumpers, beds, and more — for non-commercial educational radio.

## Setup

1. **Install Pure Data vanilla** (0.54 or later) from https://puredata.info
2. Open Pd. Go to **Help > Find Externals**. Search **"else"**. Click **Install**.
3. Download or clone this toolkit to any location.
4. Open **`console.pd`**. This is the main workspace. DSP starts automatically.

That's it. Pd vanilla + ELSE is the only dependency for making audio.

## Quick Start

1. In the **Source Bay**, click **Open** on a source slot and choose a module (e.g., `osc-bank.pd`).
2. Toggle the source **ON** and bring up the **Level** slider. You should hear sound immediately.
3. The signal passes through **Tape Warmth** and **Space** by default — everything already has the station sound.
4. Use the **Send** knob to route signal to the effects bus (Chorus, Filter, Tremolo).
5. Open the **Sequencer** to drive modules with note/gate patterns.
6. When you hear something you like, set the **Asset Type** and **Name** in the Recording section, then toggle **REC**.
7. Toggle REC again to stop. Your WAV is saved to `export/<type>/`.
8. After your session, double-click **`Export Session.command`** (or run `./scripts/post-session.sh`) to normalize, convert to MP3, and tag for LibreTime.

## Source Modules

| Module | File | What It Does |
|--------|------|-------------|
| **Analog Oscillator Bank** | `modules/osc-bank.pd` | Two-oscillator synth with filter and ADSR. Leads, basses, melodic lines. |
| **Chord Pad** | `modules/chord-pad.pd` | Multi-voice detuned chord drone. The go-to for beds under speech. |
| **FM Voice** | `modules/fm-voice.pd` | Two-operator FM synth. Bells, metallic hits, warm keys. |
| **Noise Sculptor** | `modules/noise-sculptor.pd` | Colored noise through resonant filter. Textures, beds, whooshes. |
| **Sample Player** | `modules/sample-player.pd` | Load and play WAV files with speed/loop/reverse controls. |
| **Drum Machine** | `modules/drum-machine.pd` | 8 synthesized voices with 16-step pattern sequencer. |
| **Mic/Line Input** | `modules/mic-input.pd` | Live audio input from your audio interface (Source 6). |

## Effects Modules

| Module | File | Type | What It Does |
|--------|------|------|-------------|
| **Tape Warmth** | `modules/tape-warmth.pd` | Inline | Saturation, head bump EQ, flutter. The station sound. |
| **Space** | `modules/space.pd` | Inline | Room reverb (ELSE free.rev~). Everything sounds like a real room. |
| **Chorus** | `modules/chorus.pd` | Send bus | Stereo modulated delay. Thickens and widens. |
| **Filter** | `modules/filter.pd` | Send bus | Resonant filter with LFO. |
| **Tremolo/Gate** | `modules/tremolo-gate.pd` | Send bus | Amplitude modulation from smooth tremolo to hard gate. |

## Control Module

| Module | File | What It Does |
|--------|------|-------------|
| **Step Sequencer** | `modules/sequencer.pd` | Generates note/gate patterns. Scale-constrained (pentatonic minor default). |

## Signal Flow

```
Source(s) ──> Insert Bus ──> Tape Warmth ──> Space ──> Master Bus ──> VU / Record
                  |                                         ^
                  +──> Send Bus ──> [Chorus|Filter|Trem] ───+
```

- **Inline effects** (Tape Warmth, Space) are always active by default with subtle settings.
- **Send effects** (Chorus, Filter, Tremolo) are on a parallel bus. Use the send knob on each source to route signal to them.
- The **sequencer** is control-only — it sends note/gate data to whichever source module you target.
- The **drum machine** has its own mixer channel with level, pan, and send controls.

## Recording & Export Workflow

### 1. Record in the console

Set the **Asset Type** (Jingle, Stinger, Sweeper, Bed, Bumper, Station ID, Promo, PSA, Other) and give it a **Name**, then toggle **REC**. WAVs are saved to `export/<type>/` directories.

### 2. Review and rename

Between sessions, review your recordings in the `export/` folders. Rename keepers to something descriptive. Move files between type folders to reclassify if needed.

### 3. Export

Double-click **`Export Session.command`** or run from the terminal:

```bash
# Standard: normalize + convert + tag
./scripts/post-session.sh

# Skip normalization (if you gain-staged manually)
./scripts/post-session.sh --skip-normalize

# Reprocess everything
./scripts/post-session.sh --force
```

The script:
1. **Scans** `export/<type>/` directories for new WAV files
2. **Normalizes** each to -16 LUFS / -1 dBTP (two-pass ffmpeg loudnorm)
3. **Converts** to 320 kbps CBR MP3
4. **Tags** with ID3 metadata (title, artist=91.9 KXST, album, genre=asset type, date)
5. **Outputs** to `EXPORTS/<type>/` — ready to upload to LibreTime
6. **Archives** processed WAVs to `export/<type>/archived/` so the filename slot is free for the next session

A manifest at `EXPORTS/manifest.txt` tracks everything that's been processed. The script is incremental — it only processes new or changed files.

### Requirements for export

- **ffmpeg** with libmp3lame encoder
- **Bash 4+** (macOS: `brew install bash`)

On macOS, the `Export Session.command` launcher checks for these and tells you what to install if anything is missing.

## Session Tips

- Start with a **Chord Pad** as a foundation, then layer other elements on top.
- Use the **send knob** on source modules to add chorus, filter sweep, or tremolo.
- The sequencer defaults to **pentatonic minor** — experiment freely, everything will sound musical.
- If connecting a MIDI keyboard, set the **MIDI channel** and **target** in the console to route to your module.
- **Record short takes.** It's easier to select the best from many options than to try to get one perfect take.
- **Name your recordings** before hitting REC — it saves time during the review step.

## File Structure

```
station-audio-toolkit/
├── README.md
├── console.pd                      <- Main console (open this)
├── Export Session.command           <- Double-click to export (macOS)
├── modules/
│   ├── osc-bank.pd                 <- Analog Oscillator Bank
│   ├── chord-pad.pd                <- Chord Pad
│   ├── fm-voice.pd                 <- FM Voice
│   ├── noise-sculptor.pd           <- Noise Sculptor
│   ├── sample-player.pd            <- Sample Player
│   ├── drum-machine.pd             <- Drum Machine
│   ├── mic-input.pd                <- Mic/Line Input
│   ├── sequencer.pd                <- Step Sequencer
│   ├── tape-warmth.pd              <- Tape Warmth (inline)
│   ├── space.pd                    <- Space/Reverb (inline)
│   ├── chorus.pd                   <- Chorus (send bus)
│   ├── filter.pd                   <- Filter (send bus)
│   └── tremolo-gate.pd             <- Tremolo/Gate (send bus)
├── export/
│   ├── jingles/                    <- Recorded WAVs by type
│   │   └── archived/               <- Processed WAVs moved here
│   ├── sweepers/
│   ├── stingers/
│   ├── beds/
│   ├── bumpers/
│   ├── station-id/
│   ├── promos/
│   ├── psa/
│   └── other/
├── EXPORTS/                        <- Processed MP3s (upload these)
│   ├── manifest.txt                <- Tracks all processed files
│   ├── jingles/
│   ├── sweepers/
│   └── ...
├── scripts/
│   └── post-session.sh             <- Post-session processing
├── presets/                        <- Preset files (per module)
└── dev/                            <- Development tools and analysis
```

## Troubleshooting

**No sound:**
Check that a source module is toggled ON and its level is above -inf. Check that the master level is up. Check Pd's audio settings (Media > Audio Settings) — the correct output device must be selected.

**Clicking or popping:**
Increase the audio buffer size in Pd's audio settings. 64 or 128 samples is often too low — try 256 or 512.

**ELSE objects not found:**
Make sure the ELSE library is installed via Deken (Help > Find Externals > "else"). Restart Pd after installing.

**MIDI not responding:**
Check Pd's MIDI settings (Media > MIDI Settings). Select your MIDI device. Ensure the MIDI channel in the console matches your controller's output channel.

**Export script errors:**
Make sure `ffmpeg` is installed and in your PATH. On macOS, install via `brew install bash ffmpeg`. Check that you have WAV files in the `export/` type directories.
