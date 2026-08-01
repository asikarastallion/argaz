# Third-Party Notices

ArgazUI itself is released under the MIT License (see [LICENSE](LICENSE)).
This file lists the third-party components it bundles, depends on, or drives,
together with their licences.

---

## 1. Bundled in this repository

These files are redistributed as part of this repository, so their licence
notices are reproduced here.

### xterm.js — MIT License

`argazui/static/vendor/xterm.js`, `argazui/static/vendor/xterm.css`,
`argazui/static/vendor/addon-fit.js`
Upstream: https://github.com/xtermjs/xterm.js

```
Copyright (c) 2017-2019, The xterm.js authors (https://github.com/xtermjs/xterm.js)
Copyright (c) 2014-2016, SourceLair Private Company (https://www.sourcelair.com)
Copyright (c) 2012-2013, Christopher Jeffrey (https://github.com/chjj/term.js)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 2. Python dependencies (installed via pip, not bundled)

| Package | Licence | Used for |
|---|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | MIT | HTTP + WebSocket server |
| [Starlette](https://github.com/encode/starlette) | BSD-3-Clause | FastAPI's ASGI foundation |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT | Request models |
| [Uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | ASGI server |
| [wsproto](https://github.com/python-hyper/wsproto) | MIT | WebSocket protocol |
| [pymavlink](https://github.com/ArduPilot/pymavlink) | **LGPL-3.0** | MAVLink command/telemetry link |
| [Pillow](https://github.com/python-pillow/Pillow) | HPND | Resizing model preview images (optional) |

**On pymavlink (LGPL-3.0):** ArgazUI imports pymavlink as an unmodified
library installed separately with pip; it is neither bundled nor modified
here. Under the LGPL this permits the calling application to carry a different
licence, provided users remain free to replace the library — which they are,
since it is an ordinary pip dependency.

---

## 3. Simulation stack (executed, not redistributed)

ArgazUI is a front end. It reads the documentation and parameter files of the
projects below from your own local clones, and launches their programs as
subprocesses. **No code from these projects is copied into or redistributed by
this repository.** Running a GPL program as a separate process does not make
the calling program a derivative work.

| Project | Licence | How ArgazUI uses it |
|---|---|---|
| [ArduPilot](https://github.com/ArduPilot/ardupilot) | GPL-3.0 | Runs `sim_vehicle.py` and the SITL binaries |
| [ardupilot_gazebo](https://github.com/ArduPilot/ardupilot_gazebo) | GPL-3.0 | Gazebo plugin, Iris/Zephyr models and worlds |
| [SITL_Models](https://github.com/ArduPilot/SITL_Models) | GPL-3.0 | Model/world/parameter files; its docs feed the model registry |
| [MAVProxy](https://github.com/ArduPilot/MAVProxy) | GPL-3.0 | Ground station launched inside the simulation terminal |
| [Gazebo](https://github.com/gazebosim) | Apache-2.0 | Physics and rendering |
| [ROS 2](https://github.com/ros2) | Apache-2.0 | DDS bridge and RViz for the Iris model |

### Model preview images

The images shown in the model picker are **not** committed to this repository.
`python3 -m argazui.fetch_images` downloads them at setup time from the
documentation of the ArduPilot `SITL_Models` and `ardupilot_gazebo` projects
into your local `argazui/static/models/` directory. They remain the property of
their respective authors under those projects' licences.

The Iris preview is a screenshot captured from a local Gazebo session; the
procedure is documented at the top of `argazui/fetch_images.py`.
