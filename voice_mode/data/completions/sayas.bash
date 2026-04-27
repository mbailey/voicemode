# bash completion for sayas
# Source this file or copy to /etc/bash_completion.d/sayas
#
# Installed by: pip install voicemode
# To activate:  eval "$(sayas --completion)"
#   or:         source $(python3 -c "from voice_mode.data.completions import get_completion_path; print(get_completion_path('sayas.bash'))")

_sayas_completion() {
    local cur prev voices_json
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    voices_json="${VOICEMODE_VOICES_JSON:-$HOME/.voicemode/voices.json}"

    # After -o, complete filenames
    if [[ "$prev" == "-o" ]]; then
        COMPREPLY=($(compgen -f -- "$cur"))
        return 0
    fi

    # First arg: voice name or flags
    if [[ $COMP_CWORD -eq 1 ]]; then
        local voices flags="-l --list --completion"
        if [[ -f "$voices_json" ]]; then
            voices=$(python3 -c "
import json
with open('$voices_json') as f:
    data = json.load(f)
print(' '.join(sorted(data.get('voices', {}).keys())))
" 2>/dev/null)
        fi
        COMPREPLY=($(compgen -W "$voices $flags" -- "$cur"))
        return 0
    fi

    # Second arg after voice name: flags
    if [[ $COMP_CWORD -eq 2 ]]; then
        COMPREPLY=($(compgen -W "-p --preview -o" -- "$cur"))
        return 0
    fi

    # Later args: flags
    if [[ "$cur" == -* ]]; then
        COMPREPLY=($(compgen -W "-o -p --preview" -- "$cur"))
        return 0
    fi

    return 0
}

complete -o default -F _sayas_completion sayas
