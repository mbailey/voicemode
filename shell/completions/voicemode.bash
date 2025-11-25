# bash completion for voicemode
_voicemode_completion() {
    local IFS=$'\n'
    local response
    
    response=$(env _VOICEMODE_COMPLETE=bash_complete COMP_WORDS="${COMP_WORDS[*]}" COMP_CWORD=$COMP_CWORD voicemode 2>/dev/null)
    
    for completion in $response; do
        IFS=',' read type value <<< "$completion"
        
        if [[ $type == 'plain' ]]; then
            COMPREPLY+=("$value")
        elif [[ $type == 'file' ]]; then
            COMPREPLY+=("$value")
        elif [[ $type == 'dir' ]]; then
            COMPREPLY+=("$value")
        fi
    done
    
    return 0
}

complete -o default -F _voicemode_completion voicemode
