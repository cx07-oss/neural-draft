"""Build a narrated, captioned walkthrough from genuine browser captures.

No simulated application states. The forge clip uses timed browser screenshots.
Requires Pillow and imageio-ffmpeg, independently of the application runtime.
"""
from pathlib import Path
import bisect
import json
import math
import subprocess
import sys
import wave

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.deps'))
import imageio_ffmpeg

W, H, FPS = 1920, 1080, 24
BG = '#08111d'
CYAN = '#77ebe5'
WHITE = '#edf4fa'
MUTED = '#adbdcd'
FONT = Path('C:/Windows/Fonts')


def font(size, bold=False):
    return ImageFont.truetype(str(FONT / ('segoeuib.ttf' if bold else 'segoeui.ttf')), size)


def wrap(draw, text, f, max_width):
    result = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split():
            test = (line + ' ' + word).strip()
            if draw.textlength(test, font=f) > max_width and line:
                result.append(line)
                line = word
            else:
                line = test
        result.append(line)
    return result


def textblock(draw, text, xy, f, color, width, line_height):
    x, y = xy
    for line in wrap(draw, text, f, width):
        draw.text((x, y), line, font=f, fill=color)
        y += line_height
    return y


def compose(scene, index, image_name=None):
    im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((40, 23), 'NEURAL—DRAFT', font=font(30, True), fill=WHITE)
    d.text((1420, 29), 'WORKING PROTOTYPE  /  OFFLINE DEMO', font=font(17), fill=CYAN)
    for n in range(16):
        x = 40 + n * 116
        d.rounded_rectangle((x, 76, x + 105, 80), radius=2, fill=CYAN if n <= index else '#243547')
    # Screenshot is fitted without stretching. Large captures retain the top
    # 950px so all shots preserve the same natural desktop scale.
    source = Image.open(ROOT / 'captures' / (image_name or scene['image'])).convert('RGB')
    if scene.get('crop'):
        source = source.crop(tuple(scene['crop']))
    elif source.height > 970:
        source = source.crop((0, 0, min(1425, source.width), 950))
    source.thumbnail((1350, 830), Image.Resampling.LANCZOS)
    x = 36 + (1350 - source.width) // 2
    y = 110 + (830 - source.height) // 2
    d.rounded_rectangle((x-2, y-2, x+source.width+2, y+source.height+2), radius=8, fill='#365064')
    im.paste(source, (x, y))
    d = ImageDraw.Draw(im)
    d.text((1440, 124), f'{index+1:02d} / 16', font=font(24), fill=CYAN)
    textblock(d, scene['chapter'], (1440, 171), font(16, True), MUTED, 430, 24)
    bottom = textblock(d, scene['title'], (1437, 218), font(43, True), WHITE, 430, 54)
    d.line((1440, bottom + 24, 1848, bottom + 24), fill='#344757', width=1)
    py = max(440, bottom + 55)
    for point in scene['points']:
        d.ellipse((1440, py+11, 1446, py+17), fill=CYAN)
        py = textblock(d, point, (1463, py), font(25), MUTED, 390, 35) + 27
    d.text((1440, 884), 'CAPTURED WALKTHROUGH', font=font(15, True), fill=CYAN)
    d.text((1440, 910), 'Synthetic voice · actual app states', font=font(15), fill=MUTED)
    d.line((40, 966, 1880, 966), fill='#263749', width=1)
    lines = wrap(d, scene['narration'], font(25), 1780)
    if len(lines) > 2:
        raise ValueError(f'Caption overflow in scene {index+1}')
    ty = 992 if len(lines) == 2 else 1006
    for line in lines:
        tw = d.textlength(line, font=font(25))
        d.text(((W-tw)/2, ty), line, font=font(25), fill=WHITE)
        ty += 34
    return im


def srt_time(seconds):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def main():
    scenes = json.loads((ROOT / 'scenes.json').read_text(encoding='utf-8'))
    build = ROOT / 'build'
    build.mkdir(exist_ok=True)
    params = None
    audio_parts = []
    total_frames = 0
    cursor = 0.0
    subtitles = []
    for index, scene in enumerate(scenes):
        with wave.open(str(ROOT / 'audio' / f'{index+1:02}.wav'), 'rb') as wav:
            current = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
            if params is not None and params != current:
                raise ValueError('Inconsistent audio format')
            params = current
            data = wav.readframes(wav.getnframes())
            seconds = wav.getnframes() / wav.getframerate()
        count = math.ceil((seconds + 0.75) * FPS)
        scene['frames'] = count
        scene['seconds'] = count / FPS
        total_frames += count
        sample_size = params[0] * params[1]
        lead = round(0.35 * params[2])
        full = round(scene['seconds'] * params[2])
        tail = full - len(data) // sample_size - lead
        audio_parts.append(b'\0' * lead * sample_size + data + b'\0' * tail * sample_size)
        subtitles.append(f'{index+1}\n{srt_time(cursor+0.35)} --> {srt_time(cursor+scene["seconds"]-0.15)}\n{scene["narration"]}\n')
        scene['start'] = cursor
        cursor += scene['seconds']
    audio_path = build / 'narration.wav'
    with wave.open(str(audio_path), 'wb') as output:
        output.setnchannels(params[0]); output.setsampwidth(params[1]); output.setframerate(params[2])
        output.writeframes(b''.join(audio_parts))
    (ROOT / 'Neural-Draft-demo.srt').write_text('\n'.join(subtitles), encoding='utf-8')
    (ROOT / 'transcript.txt').write_text('\n\n'.join(f'{i+1:02}. {s["chapter"]}\n{s["narration"]}' for i, s in enumerate(scenes)), encoding='utf-8')
    (build / 'timeline.json').write_text(json.dumps(scenes, indent=2), encoding='utf-8')
    previews = [compose(scene, i) for i, scene in enumerate(scenes)]
    sheet = Image.new('RGB', (1920, 1080), BG)
    for i, preview in enumerate(previews):
        preview.save(build / f'scene-{i+1:02}.png')
        thumb = preview.resize((480, 270), Image.Resampling.LANCZOS)
        sheet.paste(thumb, ((i%4)*480, (i//4)*270))
    sheet.save(build / 'contact-sheet.jpg', quality=90)
    output_path = ROOT / 'Neural-Draft-demo.mp4'
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg, '-y', '-hide_banner', '-loglevel', 'warning', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
           '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', str(audio_path), '-c:v', 'libx264',
           '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k',
           '-movflags', '+faststart', '-shortest', str(output_path)]
    print(f'Rendering {cursor:.2f}s at {W}x{H}, {FPS}fps; {total_frames} frames.', flush=True)
    with (build / 'encode.log').open('w', encoding='utf-8') as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=log)
        done = 0
        previous = Image.new('RGB', (W, H), BG)
        for index, scene in enumerate(scenes):
            animation = []
            if scene.get('animation'):
                entries = json.loads((ROOT / 'captures' / scene['animation']).read_text())
                animation = [(item['ms']/1000, compose(scene,index,item['file'])) for item in entries]
            for frame_index in range(scene['frames']):
                t = frame_index / FPS
                base = previews[index]
                if animation and t < animation[-1][0]:
                    ai = min(bisect.bisect_left([a[0] for a in animation],t),len(animation)-1)
                    base = animation[ai][1]
                if frame_index < 8:
                    frame = Image.blend(previous,base,(frame_index+1)/8)
                else:
                    frame = base.copy()
                d = ImageDraw.Draw(frame)
                d.rectangle((0,H-4,round(W*(done+1)/total_frames),H),fill=CYAN)
                proc.stdin.write(frame.tobytes())
                done += 1
            previous = previews[index]
            print(f'Scene {index+1:02}/16 complete: {scene["chapter"]}',flush=True)
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError((build/'encode.log').read_text())
    print(f'Video complete: {output_path} ({output_path.stat().st_size/1024/1024:.1f} MB)',flush=True)


if __name__ == '__main__':
    main()
