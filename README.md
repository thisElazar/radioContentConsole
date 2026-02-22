# Station Audio Toolkit

A Pure Data (Pd) interactive audio toolkit for producing broadcast-quality audio elements — jingles, sweepers, stingers, bumpers, beds, and more — for non-commercial educational radio.

## Setup

1. **Install Pure Data vanilla** (0.54 or later) from https://puredata.info
2. Open Pd. Go to **Help > Find Externals**. Search **"else"**. Click **Install**.
3. Download or clone this toolkit to any location.
4. Open **`console.pd`**. This is the main workspace.

That's it. Pd vanilla + ELSE is the only dependency.

## Quick Start

1. In the **Source Bay**, click a module selector and choose "Analog Oscillator Bank."
2. Toggle the module **ON**. You should immediately hear a warm, detuned sawtooth tone.
3. The sound passes through **Tape Warmth** and **Space** by default — everything already has the station sound.
4. Try the presets: click "Warm Bass," "Bright Lead," etc.
5. Open the **Sequencer**. Click **Run**. The default pattern drives the oscillator.
6. When you hear something you like, set the **Asset Type** in the Recording Section, then click **Record**.
7. When done, click Record again to stop. Your WAV is saved to `export/raw/`.
8. After your session, run the post-session script to normalize, convert to MP3, and tag for LibreTime:

```bash
./scripts/post-session.sh
```

## Source Modules

| Module | File | What It Does |
|--------|------|-------------|
| **Analog Oscillator Bank** | `modules/osc-bank.pd` | Two-oscillator synth with filter and ADSR. Leads, basses, melodic lines. |
| **Noise Sculptor** | `modules/noise-sculptor.pd` | Colored noise through resonant filter. Textures, beds, whooshes. |
| **FM Voice** | `modules/fm-voice.pd` | Two-operator FM synth. Bells, metallic hits, warm keys. |
| **Chord Pad** | `modules/chord-pad.pd` | Multi-voice detuned chord drone. The go-to for beds under speech. |
| **Sample Player** | `modules/sample-player.pd` | Load and play WAV files with speed/loop/reverse controls. |

## Effects Modules

| Module | File | Type | What It Does |
|--------|------|------|-------------|
| **Tape Warmth** | `modules/tape-warmth.pd` | Inline | Saturation, head bump EQ, flutter. The station sound. |
| **Space** | `modules/space.pd` | Inline | Room reverb (freeverb). Everything sounds like a real room. |
| **Chorus** | `modules/chorus.pd` | Send bus | Stereo modulated delay. Thickens and widens. |
| **Filter** | `modules/filter.pd` | Send bus | Resonant filter with LFO and envelope follower. |
| **Tremolo/Gate** | `modules/tremolo-gate.pd` | Send bus | Amplitude modulation from smooth tremolo to hard gate. |

## Control Module

| Module | File | What It Does |
|--------|------|-------------|
| **Step Sequencer** | `modules/sequencer.pd` | Generates note/gate patterns. Scale-constrained (pentatonic minor default). |

## Signal Flow

```
Source(s) ──→ Insert Bus ──→ Tape Warmth ──→ Space ──→ Master Bus ──→ VU / Record
                  │                                         ↑
                  └──→ Send Bus ──→ [Chorus│Filter│Trem] ───┘
```

- **Inline effects** (Tape Warmth, Space) are always active by default with subtle settings.
- **Send effects** (Chorus, Filter, Tremolo) are on a parallel bus. Use the send knob on each source to route signal to them.
- The **sequencer** is control-only — it sends note/gate data to whichever source module you target.

## Session Tips

- Start with a **Chord Pad** on "Warm Bed" as a foundation, then layer other elements on top.
- Use the **send knob** on source modules to add chorus, filter sweep, or tremolo.
- The sequencer defaults to **pentatonic minor** — experiment freely, everything will sound musical.
- If connecting a MIDI keyboard, set the **MIDI target** in the console to whichever module you want to play.
- **Record short takes.** It's easier to select the best from many options than to try to get one perfect take.

## Post-Session Processing

After a creative session, run the post-session script from the toolkit directory:

```bash
# Standard: normalize + convert + tag
./scripts/post-session.sh

# Skip normalization (if you gain-staged manually)
./scripts/post-session.sh --skip-normalize

# Custom station name for ID3 tags
./scripts/post-session.sh --station "Delta Community Radio"
```

The script:
1. **Normalizes** each WAV to -16 LUFS / -1 dBTP (two-pass ffmpeg loudnorm)
2. **Converts** to 320 kbps CBR MP3
3. **Tags** with ID3 metadata (title, artist, album, genre=asset type, date)
4. **Sorts** into `export/` subdirectories by asset type

The `export/` directory (minus `raw/`) is ready to drag into LibreTime's upload interface. The **Genre** tag carries the asset type, so LibreTime smart blocks can filter by type automatically.

### Requirements for post-session script

- `ffmpeg` with `libmp3lame` encoder
- `bash` 4.0+

## File Structure

```
station-audio-toolkit/
├── README.md
├── console.pd                  ← Main console (always open)
├── modules/
│   ├── osc-bank.pd             ← Analog Oscillator Bank
│   ├── noise-sculptor.pd       ← Noise Sculptor
│   ├── fm-voice.pd             ← FM Voice
│   ├── chord-pad.pd            ← Chord Pad
│   ├── sample-player.pd        ← Sample Player
│   ├── sequencer.pd            ← Step Sequencer
│   ├── tape-warmth.pd          ← Tape Warmth (inline)
│   ├── space.pd                ← Space/Reverb (inline)
│   ├── chorus.pd               ← Chorus (send bus)
│   ├── filter.pd               ← Filter (send bus)
│   └── tremolo-gate.pd         ← Tremolo/Gate (send bus)
├── presets/                    ← Preset files (per module)
├── export/
│   ├── raw/                    ← Original WAVs + manifest.txt
│   ├── jingles/
│   ├── sweepers/
│   ├── stingers/
│   ├── bumpers/
│   ├── beds/
│   ├── station-id/
│   ├── psa/
│   ├── promos/
│   └── other/
└── scripts/
    └── post-session.sh         ← Post-session processing
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

**post-session.sh errors:**
Make sure `ffmpeg` is installed and in your PATH. Check that `export/raw/manifest.txt` exists (it's created automatically when you record in the toolkit).
