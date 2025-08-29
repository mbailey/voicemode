# Installing npm Global Packages Without sudo on macOS/Linux

This guide explains how to configure npm to install global packages without requiring root permissions on macOS and Linux.

## Why This Matters

By default, npm installs global packages to `/usr/local`, which requires sudo access. This can cause:
- Permission errors
- Security concerns from running npm with elevated privileges
- Conflicts with system-installed Node.js

## Quick Setup

We provide an automated setup script that handles all the configuration for you:

**Option 1: Download and run directly**
```bash
curl -fsSL https://raw.githubusercontent.com/mbailey/voicemode/master/scripts/setup-npm-global.sh | bash
```

**Option 2: Run from cloned repository**
```bash
./scripts/setup-npm-global.sh
```

The script will:
- Create the `~/.npm-global` directory
- Configure npm to use this directory
- Add the directory to your PATH
- Update your shell configuration file

## Manual Setup

If you prefer to configure manually, follow these steps:

### 1. Create npm Global Directory

```bash
mkdir -p ~/.npm-global
```

### 2. Configure npm to Use This Directory

```bash
npm config set prefix '~/.npm-global'
```

### 3. Add npm Global bin to Your PATH

Add this line to your shell configuration file (`~/.zshrc` for Zsh or `~/.bash_profile` for Bash):

```bash
export PATH="$HOME/.npm-global/bin:$PATH"
```

### 4. Reload Your Shell Configuration

```bash
# For Zsh
source ~/.zshrc

# For Bash
source ~/.bash_profile
```

## Verification

Test by installing a package globally without sudo:

```bash
# This should work without sudo
npm install -g @google/gemini-cli
```

## Alternative: Using Node Version Managers

For even better Node.js management, consider using:

- **[nvm](https://github.com/nvm-sh/nvm)** - Node Version Manager
- **[fnm](https://github.com/Schniz/fnm)** - Fast Node Manager
- **[volta](https://volta.sh/)** - JavaScript Tool Manager

These tools install Node.js and npm in your home directory by default, avoiding permission issues entirely.

### Example with nvm:

```bash
# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install | bash

# Install latest Node.js
nvm install node

# Global packages now install to ~/.nvm without sudo
npm install -g @google/gemini-cli
```

## Troubleshooting

### Permission Errors Still Occur

Check that your PATH is correctly set:
```bash
echo $PATH
which npm
```

### Previously Installed Packages Not Found

You may need to reinstall global packages after changing the prefix:
```bash
npm list -g --depth=0
```

### Reset to Default Settings

To revert these changes:
```bash
npm config delete prefix
# Remove the PATH export from your shell config file
```

## See Also

- [npm Documentation: Fixing npm permissions](https://docs.npmjs.com/resolving-eacces-permissions-errors-when-installing-packages-globally)
- [Node.js Download Page](https://nodejs.org/en/download/)
- [Homebrew Node Formula](https://formulae.brew.sh/formula/node)