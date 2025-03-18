# echogit: Localized Data Synchronization via Git

The way i work is everything is a git project. Except for the music projects, photos projects and video that are rsync projects.
You get it, almost everything are texts files inside git projects :
- personal notes: markdown projects organized in various folders
- cv: LaTeX project
- /etc folder: managed by etckeeper
- ~/.config : git project
- contacts: vcf files stored in various folders, with one folder pear category
- todo: managed by todo.txt (text files)
- password: managed by pass program (text files)
- etc

I also don't want to store my personal data in the cloud: I don't need to do so as I have enough devices for redundancy. 
To make things easier, i did this python project and I share it on MIT license, even if i doubt that there will be others tech user that would find convenient the way I manage my files.


## Description:

<img align="left" width="100" height="100" src="docs/icon.png">

Echogit is designed for synchronization of data across multiple devices without the need for an internet connection. Utilizing the robustness of git and the security of SSH, it offers a decentralized approach to manage and sync various types of data.
<br>
<br>

## Core Features:

- Local Synchronization: Synchronize data across your devices using your local network, reducing reliance on cloud services.
- Git-Based: Leverages git's version control capabilities for efficient and reliable data tracking.
- SSH Security: Employs SSH for secure data transfer, ensuring your information remains private and secure.

## Targeted users:

Tech-savvy individuals who prefer local data management, are comfortable with git and SSH.

## Requirements

Echogit uses SSH and Git to synchronize projects between peers. To sync, you need to ensure that:

1. You have set up SSH key authentication between your local machine and each peer. This avoids the need for password entry during synchronization.

You can copy your SSH public key to a peer by running:
   ```bash
   ssh-copy-id user@peer_host
   ```

## Usage

### Synchronizing Projects


Use the following command to sync a folder:

```bash
echogit sync [folder]
```

### Listing Projects

```bash
echogit list [folder] --remote -p peer_name
```

### Running in TUI Mode

```bash
echogit tui
```

## Android support

There is an Android version called echogit-mobile. It provides a UI to control the normal Echogit application through Termux and the Termux API. This allows you to manage synchronization on Android devices, using the same functionality available on the desktop version.

## Tests

Run the test with:

```bash
> pytest
```
