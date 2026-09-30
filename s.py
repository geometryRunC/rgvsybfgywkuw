import os
import shlex
import subprocess
from flask import Flask, request, send_from_directory

app = Flask(__name__)

API_TOKEN = "kcbp_term"

HOME_DIR = os.path.expanduser("~")
CURRENT_DIR = HOME_DIR

MEDIA_EXTENSIONS = {
    ".mp4",
    ".webm",
    ".mov",
    ".avi",
    ".mkv",
    ".gif",
    ".png",
    ".jpg",
    ".jpeg",
}


def get_prompt():
    global CURRENT_DIR
    if CURRENT_DIR == HOME_DIR:
        formatted_path = "~"
    elif CURRENT_DIR.startswith(HOME_DIR):
        formatted_path = "~" + CURRENT_DIR[len(HOME_DIR) :]
    else:
        formatted_path = CURRENT_DIR
    return f"{formatted_path}$ "


@app.route("/cmd", methods=["GET"])
def execute_command():
    global CURRENT_DIR

    token = request.args.get("token")
    if token != API_TOKEN:
        return "Error: Unauthorized", 401

    raw_command = request.args.get("args")
    if not raw_command:
        return "Error: No command provided", 400

    prompt = get_prompt()

    try:
        args = shlex.split(raw_command)
        args = [os.path.expanduser(arg) for arg in args]

        # Handle 'cd' internal navigation
        if args[0] == "cd":
            target = args[1] if len(args) > 1 else HOME_DIR
            new_path = os.path.abspath(os.path.join(CURRENT_DIR, target))

            if os.path.exists(new_path) and os.path.isdir(new_path):
                CURRENT_DIR = new_path
                return f"{prompt}{raw_command}\n{get_prompt()}"
            else:
                return f"{prompt}{raw_command}\ncd: no such file or directory: {target}"

        files_before = set(os.listdir(CURRENT_DIR))

        result = subprocess.run(
            args, capture_output=True, text=True, timeout=60, cwd=CURRENT_DIR
        )

        files_after = set(os.listdir(CURRENT_DIR))
        new_files = files_after - files_before

        created_media = [
            f
            for f in new_files
            if os.path.splitext(f)[1].lower() in MEDIA_EXTENSIONS
        ]

        command_output = result.stdout + result.stderr
        response_text = f"{prompt}{raw_command}"

        if command_output.strip():
            response_text += f"\n{command_output.strip()}"

        if created_media:
            output_filename = created_media[0]
            scheme = request.headers.get("X-Forwarded-Proto", "https")
            host = request.headers.get("X-Forwarded-Host", request.host)

            rel_file_path = os.path.relpath(
                os.path.join(CURRENT_DIR, output_filename), start=HOME_DIR
            )
            file_url = f"{scheme}://{host}/files/{rel_file_path}"

            # Append raw URL so Discord embeds it naturally
            response_text += f"\n{file_url}"

        return response_text

    except subprocess.TimeoutExpired:
        return f"{prompt}{raw_command}\nError: Command timed out after 60 seconds.", 408
    except FileNotFoundError:
        return f"{prompt}{raw_command}\nError: Executable '{args[0]}' not found.", 404
    except Exception as e:
        return f"{prompt}{raw_command}\nError: {str(e)}", 500


@app.route("/files/<path:filename>", methods=["GET"])
def serve_file(filename):
    return send_from_directory(HOME_DIR, filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
