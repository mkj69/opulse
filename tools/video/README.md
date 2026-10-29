# Opulse video production

`storyboard.yaml` defines the scene order, durations, English and Chinese captions, capture
settings, and camera motion. `record.py` uses Chrome to save one numbered PNG for each widget
state. It also saves `boxes.json` with the capture padding, device scale, and a set of focus boxes
for every state. `compose.py` uses those images and boxes to make the video, poster, and WebVTT
caption tracks.

## Recording a scene

A scene names a page with `path` and a widget with `selector`. `width` sets the widget width in
CSS pixels before capture. `states.range` moves a slider from `from` through `to`; `to: max` uses
the slider maximum. `states.query` reloads the page for each numbered URL value. `states.ready`
can wait for each value to appear. A scene with `states: {}` records one image. A `card` scene
renders its text directly on the image.

`states.sequence` records interactions in order without reloading the page. Each list item can
set `click` to a CSS selector inside the scene's `selector`, `wait` to a CSS selector inside that
same root or a JavaScript expression, `settle` to a pause in seconds (default `0.3`), and
`capture` to `false` to skip the image (default `true`). The recorder clicks, waits, settles,
then captures the image and focus boxes. An item without `click` captures the current state;
this can be the first item. Prefix a JavaScript wait with `js:` when its form could be mistaken
for a CSS selector. The expression must become truthy before recording continues.

```yaml
states:
  sequence:
    - {wait: ".panel.is-ready"}
    - {click: ".tabs button:nth-child(2)", wait: 'js: document.querySelector(".tabs button:nth-child(2)").getAttribute("aria-selected") === "true"'}
    - {click: ".cuts button:nth-child(3)", wait: ".cuts button:nth-child(3)[aria-pressed='true']"}
```

If a page contains several similar widgets, `match` is a CSS selector for all candidates and
`index` picks the zero based Nth match. The recorder assigns that element the ID
`opulse-video-target`, which the scene can use as its `selector`. For example, `match:
"figure.op-blogfig"` and `index: 4` select the fifth figure.

`record.py` hides the page content above the widget and moves the page to the top before capture.
The entire widget, including any `pad`, must fit inside `capture.viewport`. If it extends below
the viewport, use the scene's `css`, `hide`, or `width` settings to frame the relevant content.
The recorder does not scroll the page to reach an oversized widget.

## Camera and timing

`focus` maps view names to CSS selectors inside the widget. For each state, the recorder measures
each selector relative to the widget and stores its box in `boxes.json`. The `full` box always
covers the widget. A focus selector can match several elements; the box covers their combined
area. If a view is missing in a later state, the composer uses the most recent earlier box for
that view.

For a scene with states, `camera.intro` shows the full widget for that many seconds before moving
to a focus view. `camera.view` is the default focus name. `camera.views` overrides it by state
index, such as `{0: top, 4: detail}`. `camera.move` sets the move duration. `camera.width` gives
a minimum camera width in CSS pixels for a focused view; the composer can use a wider frame to
fit the entire focus box. `camera.margin` adds space around the box. `camera.lock_x: true` keeps
the camera centered on the widget horizontally. Without an explicit camera, the whole widget is
shown.

For a single image, `camera.keys` gives timed camera targets. Each key has `at` in seconds and a
`view` name. A key may also have `width` and `align`. `width` sets a minimum camera width, while
`align` positions a fixed width frame horizontally across the focus box. The composer moves
between successive keys. To fit an entire figure image, use its focus view without `width` or
`align`.

`hold_first` and `hold_last` fix the time spent on the first and last states. `holds` fixes other
state durations by zero based index, for example `{4: 2.8}`. Unspecified states share the
remaining scene time. `state_fade` controls the crossfade between states. `transition` sets the
scene crossfade, and a scene can override it with `transition_in`.

## Build and run

Run `tools/video/make_video.sh` from any directory. It changes to the repository root, builds the
English and Chinese sites, starts a server on port 8770 if needed, records each theme, composes
each video, and writes one second frame samples and numbered 4 by 4 contact sheets for each theme.
It prints the video durations and output file sizes. A server started by the script stops when the
script exits.

```bash
tools/video/make_video.sh
MASTER_TREE=/path/to/other/checkout tools/video/make_video.sh --scene growth
SKIP_BUILD=1 tools/video/make_video.sh --scene growth
THEMES=dark SKIP_BUILD=1 tools/video/make_video.sh
```

`SITE_DIR` sets the built site directory. Its default is
`tools/video/output/site` under the repository root.
`MASTER_TREE` optionally builds a second checkout's English site into `SITE_DIR/m`. The blog
scenes use this checkout's `/blog/` page. `SKIP_BUILD=1` reuses an existing site. `FRAMES` defaults to
`tools/video/output/frames`, `OUT` to `docs/assets/video`, and `SHEETS` to
`tools/video/output/sheets`. `THEMES` defaults to `light dark`. `PY` defaults to
the `python3` command on `PATH`. Extra arguments go to `record.py`.

`record.py --theme light` and `record.py --theme dark` write frames under
`FRAMES/light/SCENE` and `FRAMES/dark/SCENE`. The recorder stores the matching Material palette
in the site's local storage before loading a scene. It also sets the matching system colour
preference and checks the page scheme. `record.py --scene ID` updates only that scene's images
for the selected theme. The composer includes every enabled scene that has a frames directory,
so existing recordings are reused. Caption edits only need a new compose run.

`compose.py --theme light` and `compose.py --theme dark` write `opulse-light.mp4`,
`opulse-light.webm`, `poster-light.jpg`, and the matching dark files. Both themes share
`captions.en.vtt` and `captions.zh.vtt`. Each MP4 must be at most 10,000,000 bytes by default.
Use `--max-bytes` to change the limit or increase `--crf-mp4` to reduce the output size.
The top-level `poster: {scene: examples_cuts, at: 6.0}` selects a frame 6 seconds into that
scene on its local timeline. The composer uses the same scene and local time for both themes,
accounting for scene transitions. Without `poster`, it uses the legacy `poster_time` value
(2 seconds by default) measured from the start of the video.
The homepage player starts with the light files in its HTML. When the user changes the site
palette, it loads the matching files, restores the playback position, and resumes playback if
the video was playing. Reduced motion keeps autoplay off and shows a play button.
