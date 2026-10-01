# Reel Generator

A **two-person AI conversation reel** generator. Give it a topic and it produces a
finished, captioned 9:16 short with two voices, a cover image, and an
Instagram-ready caption, then publishes it.

## Pipeline

The source is split into numbered stage packages that run in order:

| Stage | Package | What it does |
| --- | --- | --- |
| 1 | `01_ideas/` | Generates topic ideas with Gemini (`idea_service.py`) and records them in Supabase (`supabase_store.py`) |
| 2 | `02_script/` | Writes the two-person dialogue script (`script_service.py`) |
| 3 | `03_tts/` | Synthesizes each line with ElevenLabs and stitches the track (`audio_service.py`) |
| 4 | `04_images/` | Character avatars (`image_service.py`) and the cover image (`cover.py`) |
| 5 | `05_captions/` | Builds ASS/SRT subtitles with per-speaker highlight colors (`subtitle_service.py`) |
| 6 | `06_video/` | Renders and burns the final MP4 (`video_service.py`) |
| 7 | `07_publish/` | Generates the Instagram caption (`caption.py`), uploads media, and posts (`instagram.py`, `storage.py`) |

Supporting modules: `main.py` (orchestrator), `config.py`, `utils.py`,
`workflow_manager.py` (job state), `generate_ideas.py` (idea batch tool).

Because the packages start with digits, they are imported with `importlib` inside
`main.py` (`_load(...)`), not with a normal `import`.

## Prerequisites

- Python 3.11+ and a virtual environment (`.venv`)
- [FFmpeg](https://ffmpeg.org/) and `ffprobe` on `$PATH`
- Accounts / keys for:
  - Groq (ideas, script, captions)
  - ElevenLabs (text to speech)
  - Cloud storage (Supabase S3, AWS S3, or Cloudflare R2)
  - Instagram Graph API (a professional/business account)

## Installation

```bash
cd /home/aditys/code/reel

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

## Configuration

Copy the example environment file and fill in your secrets:

```bash
cp .env.example .env   # then edit .env
```

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Idea generation (Google Gemini) |
| `GROQ_API_KEY`, `GROQ_MODEL` | Script and caption generation |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_MODEL_ID` | Text to speech |
| `DEFAULT_VOICE_A`, `DEFAULT_VOICE_B` | ElevenLabs voice IDs for Alex and Sam |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_IDEAS_TABLE` | Records generated ideas |
| `STORAGE_*` | Cloud bucket used for the video and cover |
| `IG_USER_ID`, `IG_ACCESS_TOKEN` | Instagram publishing |
| `DRY_RUN_MODE` | `true` simulates uploads/publishing |
| `COVER_INTRO_SEC` | Seconds the cover is shown as the first frame (default `1.5`, `0` disables) |
| `LAYOUT`, `SPLIT_TOP_RATIO` | Default video layout (`full`/`split`) and top-panel share |

## Recording ideas in Supabase

Every generated idea is saved to a Supabase table so you have a record of what has
been produced. Each row has:

- `id` - unique Supabase id (uuid)
- `index` - position of the idea in its batch, starting at `1`
- `title`, `hook`, `summary` - the idea text
- `topic`, `tone` - what was requested
- `video_generated` - `false` for every new idea
- `created_at`

Create the table once by pasting `supabase/schema.sql` into the Supabase SQL
editor, or run the checker which prints the SQL for you:

```bash
python3 setup_supabase.py
```

The SQL editor for this project:
<https://supabase.com/dashboard/project/jszsasfibqdmtbejbybp/sql/new>

## Usage

Run the full pipeline for a topic (default *Git vs GitHub*):

```bash
python3 main.py --topic "Docker vs Kubernetes"
```

It generates ideas, writes the script, synthesizes audio, builds subtitles and a
cover, renders the MP4, then generates a caption and publishes (unless
`DRY_RUN_MODE=true`).

Generate a batch of ideas to a JSON file without rendering anything:

```bash
python3 generate_ideas.py --topic "Everyday tech" --count 20
# writes data/ideas.json and saves the ideas to Supabase
```

Add `--no-supabase` to write only the JSON file.

All artefacts for a run are stored under `jobs/<job_id>/` (audio, subtitles,
storyboard segments, `cover.jpg`, and `final_video.mp4`).

## Autopilot (unattended posting)

`autopilot.py` posts reels on its own. Each cycle it:

1. Picks the next idea from Supabase with `video_generated = false`, starting at
   `index` 1 and moving upward.
2. Runs the full pipeline on it using the `photo/01` storyboard.
3. Marks that row as `video_generated = true`.

Cycles are spaced by a random interval between 1h 00m and 1h 10m.

```bash
python3 autopilot.py                 # run forever
python3 autopilot.py --once          # a single cycle
python3 autopilot.py --dry-run       # show the next idea, change nothing
python3 autopilot.py --min-minutes 60 --max-minutes 70 --photo-set 01
```

Stop it with `Ctrl+C`. Keep it running under `nohup`, `tmux`, or a systemd
service if you want it to survive a logout.

The `service_role` role needs UPDATE permission on the table, otherwise the
autopilot cannot flip `video_generated` to true. If your table already exists,
run this once in the Supabase SQL editor:

```sql
grant usage on schema public to service_role;
grant select, insert, update, delete on public.ideas to service_role;
```

## Storyboard images

Storyboards live in subfolders of `photo/`, for example:

- `photo/01/` is man + man
- `photo/02/` is man + woman

By default one folder is chosen **at random for each run** so the two characters
stay consistent across the whole reel, and its images are cycled one per line.
The first image is also the base for the cover (title overlaid on a darkened
lower half). Force a specific folder with `--photo-set`:

```bash
python3 main.py --topic "Docker vs Kubernetes" --photo-set 02
```

## Split-screen layout

Add a background clip (for example gameplay footage) to the `video/` folder and
run with `--layout split`. The two characters are cropped to their content, placed
in a white panel on top with the title as a header, and the background clip is
looped underneath. Subtitles are burned over the clip.

```bash
python3 main.py --topic "Git vs GitHub" --layout split --photo-set 01 --no-publish
```

- `--gameplay` picks a clip by path, by filename inside `video/`, or `random`
  (default).
- The split cover (character panel + a frame of the clip) is the reel's first
  frame and the Instagram cover.
- Add `--no-publish` to render locally without posting.
- `autopilot.py` defaults to this layout; pass `--layout full` to it to opt out.
- Tune the split with `SPLIT_TOP_RATIO` (default `0.583`, i.e. characters on top
  ~58%, clip below ~42%).

## Dry-run mode

Set `DRY_RUN_MODE=true` in `.env` to skip real uploads and Instagram calls. The
pipeline still renders the video and logs mock URLs and IDs.

## Notes

- Scripts are written in simple, everyday words and avoid long dashes.
- Subtitles highlight each speaker in a different color: Alex is yellow, Sam is cyan.
- The cover image is used as the reel's first frame (for `COVER_INTRO_SEC`
  seconds) and as the Instagram cover. It shows the idea's title.

## License

Provided under the MIT License.
