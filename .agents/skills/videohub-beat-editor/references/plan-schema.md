# Beat Edit Plan Schema

## Top level

```json
{
  "schema_version": "1.0",
  "audio": "absolute/or/job-relative/path",
  "fps": 30,
  "total_frames": 456,
  "duration_sec": 15.2,
  "segments": []
}
```

## Segment

```json
{
  "index": 1,
  "frames": 33,
  "output_start_frame": 0,
  "output_end_frame": 33,
  "source": "F:/media/source.mp4",
  "source_center_sec": 1230.0,
  "source_start_sec": 1229.45,
  "focus_x": 0.5,
  "focus_y": 0.5,
  "scene": "Mount Fuji and pagoda",
  "quality_score": 0.82
}
```

## Constraints

- `index` starts at 1 and is continuous.
- `frames` is a positive integer.
- `sum(segments[].frames) == total_frames`.
- `output_start_frame` equals the sum of preceding segment frames.
- `output_end_frame == output_start_frame + frames`.
- `source_start_sec >= 0`.
- The source must contain at least `frames / fps` seconds after `source_start_sec`.
- `focus_x` and `focus_y` are normalized values from 0 to 1.
- Keep frame counts unchanged when replacing or reordering source shots.

## Ratio presets

| Name | Width | Height |
|---|---:|---:|
| `16:9` | 1920 | 1080 |
| `3:4` | 1080 | 1440 |
| `4:3` | 1440 | 1080 |
| `9:16` | 1080 | 1920 |
| `1:1` | 1080 | 1080 |

For non-landscape ratios, inspect every shot. Center cropping is only a draft; set per-shot focus
coordinates or use a designed layout when the important subject cannot fit.
