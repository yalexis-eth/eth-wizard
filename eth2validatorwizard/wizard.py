import os
import subprocess
import httpx
import hashlib
import shutil
import time

from pathlib import Path

from eth2validatorwizard.constants import *

from prompt_toolkit.shortcuts import button_dialog, radiolist_dialog

def run():
    # Main entry point for the wizard.

    if not show_welcome():
        # User asked to quit
        quit()

    self_update()

    if not has_su_perm():
        # User is not a super user
        show_not_su()
        quit()

    # TODO: Detect if installation is already started and resume if needed

    if not explain_overview():
        # User asked to quit
        quit()

    # TODO: Check for open ports
    # TODO: Check for disk size
    # TODO: Check for disk speed
    # TODO: Check for internet speed
    # TODO: Check time synchronization and configure it if needed

    selected_network = select_network()
    if not selected_network:
        # User asked to quit
        quit()

    if not install_geth(selected_network):
        # User asked to quit or error
        quit()

    # TODO: Verify proper Geth installation and syncing

    if not install_lighthouse(selected_network):
        # User asked to quit or error
        quit()

    # TODO: Verify proper Lighthouse beacon node installation and syncing

    generated_keys = generate_keys(selected_network)
    if not generated_keys:
        # User asked to quit or error
        quit()
    
    if not install_lighthouse_validator(selected_network, generated_keys):
        # User asked to quit or error
        quit()

    # TODO: Verify proper Lighthouse validator client installation and the connection with the beacon node

    # Deposit via launchpad

    # TODO: Monitor

    print('Ended normally with network', selected_network)
    print('Generated keys are', generated_keys)

def show_welcome():
    # Show a welcome message about this wizard

    result = button_dialog(
        title='Eth2 Validator Wizard',
        text=(
'''
Welcome to the Eth2 Validator Wizard!

This setup assistant is meant to guide anyone through the different steps
to become a fully functional validator on the Ethereum 2.0 network. It will
install and configure all the software needed to become a validator.

If you have any question or if you need additional support, make sure
to get in touch with the ethstaker community on:

* Discord: discord.gg/e84CFep
* Reddit: reddit.com/r/ethstaker
'''     ),
        buttons=[
            ('Start', True),
            ('Quit', False)
        ]
    ).run()

    return result

def self_update():
    # TODO: Check for a new version of the wizard and self-update if needed

    pass

def has_su_perm():
    # Check to see if the script has super user (root or sudo) permissions

    return os.geteuid() == 0

def show_not_su():
    # Show a message about the wizard not having super user (root or sudo) permissions

    button_dialog(
        title='Not a super user',
        text=(
'''
The Eth2 Validator Wizard needs to have super user permissions in order
to proceed.

A simple way to give the wizard these permissions is to start it with sudo.
'''     ),
        buttons=[
            ('Quit', False)
        ]
    ).run()

def explain_overview():
    # Explain the overall process of becoming a validator

    result = button_dialog(
        title='Becoming a validator',
        text=(
'''
Here is an overview of the different steps required to become an active
validator on an Ethereum 2.0 network.

* Consolidate 32 ETH for each active validator you want (You can have
an almost unlimited amount of active validators using a single computer
and this setup)
* Install an Eth1 client and let it synchronize
* Install an Eth2 beacon node and let it synchronize
* Generate your validator(s) keys
* Install an Eth2 validator client and import your key(s)
* Perform the 32 ETH deposit for each validator
* Wait for your validator(s) to become active (can take a few hours/days)
'''     ),
        buttons=[
            ('Keep going', True),
            ('Quit', False)
        ]
    ).run()

    return result

def select_network():
    # Prompt for the selection on which network to perform the installation

    result = radiolist_dialog(
        title='Network selection',
        text=(
'''
This wizard supports installing and configuring software for various
Ethereum 2.0 networks. Mainnet is the main network with real value. The
others are mostly for testing and they do not use anything of real value.

For which network would you like to perform this installation?

* Press the tab key to switch between the controls below
'''
        ),
        values=[
            (NETWORK_MAINNET, "Mainnet"),
            (NETWORK_PYRMONT, "Pyrmont")
        ],
        ok_text='Use this',
        cancel_text='Quit'
    ).run()

    return result

def install_geth(network):
    # Install geth for the selected network

    result = button_dialog(
        title='Geth installation',
        text=(
'''
This next step will install Geth, an Eth1 client.

It uses the official Ethereum Personal Package Archive (PPA) meaning that
it gets integrated with the normal updates for Ubuntu and its related
tools like APT.

Once the installation is completed, it will create a systemd service that
will automatically start Geth on reboot or if it crashes. Geth will be
started and you will slowly start syncing with the Ethereum 1.0 network.
This syncing process can take a few hours or days even with good hardware
and good internet.
'''     ),
        buttons=[
            ('Install', True),
            ('Quit', False)
        ]
    ).run()

    if not result:
        return result

    # Install Geth from PPA
    subprocess.run([
        'add-apt-repository', '-y', 'ppa:ethereum/ethereum'])
    subprocess.run([
        'apt', 'update'])
    subprocess.run([
        'apt', 'install', 'geth'])
    
    # Setup Geth user and directory
    subprocess.run([
        'useradd', '--no-create-home', '--shell', '/bin/false', 'goeth'])
    subprocess.run([
        'mkdir', '-p', '/var/lib/goethereum'])
    subprocess.run([
        'chown', '-R', 'goeth:goeth', '/var/lib/goethereum'])
    
    # Setup Geth systemd service
    with open('/etc/systemd/system/geth.service', 'w') as service_file:
        service_file.write(GETH_SERVICE_DEFINITION[network])
    subprocess.run([
        'systemctl', 'daemon-reload'])
    subprocess.run([
        'systemctl', 'start', 'geth'])
    subprocess.run([
        'systemctl', 'enable', 'geth'])
    
    return True

def install_lighthouse(network):
    # Install Lighthouse for the selected network

    result = button_dialog(
        title='Lighthouse installation',
        text=(
'''
This next step will install Lighthouse, an Eth2 client that includes a
beacon node and a validator client in the same binary.

It will download the official binary from GitHub, verify its PGP signature
and extract it for easy use.

Once installed locally, it will create a systemd service that will
automatically start the Lighthouse beacon node on reboot or if it crashes.
The beacon node will be started and you will slowly start syncing with the
Ethereum 2.0 network. This syncing process can take a few hours or days
even with good hardware and good internet.
'''     ),
        buttons=[
            ('Install', True),
            ('Quit', False)
        ]
    ).run()

    if not result:
        return result
    
    # Getting latest Lighthouse release files
    lighthouse_gh_release_url = GITHUB_REST_API_URL + LIGHTHOUSE_LATEST_RELEASE
    headers = {'Accept': GITHUB_API_VERSION}
    response = httpx.get(lighthouse_gh_release_url, headers=headers)

    if response.status_code != 200:
        # TODO: Better handling for network response issue
        return False
    
    release_json = response.json()

    if 'assets' not in release_json:
        # TODO: Better handling on unexpected response structure
        return False
    
    binary_asset = None
    signature_asset = None

    for asset in release_json['assets']:
        if 'name' not in asset:
            continue
        if 'browser_download_url' not in asset:
            continue
    
        file_name = asset['name']
        file_url = asset['browser_download_url']

        if file_name.endswith('x86_64-unknown-linux-gnu.tar.gz'):
            binary_asset = {
                'file_name': file_name,
                'file_url': file_url
            }
        elif file_name.endswith('x86_64-unknown-linux-gnu.tar.gz.asc'):
            signature_asset = {
                'file_name': file_name,
                'file_url': file_url
            }

    if binary_asset is None or signature_asset is None:
        # TODO: Better handling of missing asset in latest release
        return False
    
    # Downloading latest Lighthouse release files
    download_path = Path(Path.home(), 'eth2validatorwizard', 'downloads')
    download_path.mkdir(parents=True, exist_ok=True)

    binary_path = Path(download_path, binary_asset['file_name'])

    with open(str(binary_path), 'wb') as binary_file:
        with httpx.stream('GET', binary_asset['file_url']) as http_stream:
            for data in http_stream.iter_bytes():
                binary_file.write(data)
    
    signature_path = Path(download_path, signature_asset['file_name'])

    with open(str(signature_path), 'wb') as signature_file:
        with httpx.stream('GET', signature_asset['file_url']) as http_stream:
            for data in http_stream.iter_bytes():
                signature_file.write(data)

    # Verify PGP signature
    command_line = ['gpg', '--keyserver', 'pool.sks-keyservers.net', '--recv-keys',
        LIGHTHOUSE_PRIME_PGP_KEY_ID]
    process_result = subprocess.run(command_line)
    if process_result.returncode != 0:
        # GPG failed to download Sigma Prime's PGP key, let's wait and retry a few times
        retry_count = 0
        while process_result.returncode != 0 and retry_count < 5:
            retry_count = retry_count + 1
            print('GPG failed to download the PGP key. We will wait 10 seconds and try again.')
            time.sleep(10)
            process_result = subprocess.run(command_line)
    
    if process_result.returncode != 0:
        # We failed to download Sigma Prime's PGP key after a few retries
        # TODO: Better handling of failed PGP key download
        return False
    
    process_result = subprocess.run([
        'gpg', '--verify', str(signature_path)])
    if process_result.returncode != 0:
        # PGP signature failed
        # TODO: Better handling of failed PGP signature
        return False
    
    # Extracting the Lighthouse binary archive
    subprocess.run([
        'tar', 'xvf', str(binary_path), '--directory', '/usr/local/bin'])
    
    # Remove download leftovers
    binary_path.unlink()
    signature_path.unlink()

    # Setup Lighthouse beacon node user and directory
    subprocess.run([
        'useradd', '--no-create-home', '--shell', '/bin/false', 'lighthousebeacon'])
    subprocess.run([
        'mkdir', '-p', '/var/lib/lighthouse/beacon'])
    subprocess.run([
        'chown', '-R', 'lighthousebeacon:lighthousebeacon', '/var/lib/lighthouse/beacon'])
    subprocess.run([
        'chmod', '700', '/var/lib/lighthouse/beacon'])
    
    # Setup Lighthouse beacon node systemd service
    with open('/etc/systemd/system/lighthousebeacon.service', 'w') as service_file:
        service_file.write(LIGHTHOUSE_BN_SERVICE_DEFINITION[network])
    subprocess.run([
        'systemctl', 'daemon-reload'])
    subprocess.run([
        'systemctl', 'start', 'lighthousebeacon'])
    subprocess.run([
        'systemctl', 'enable', 'lighthousebeacon'])
    
    return True

def generate_keys(network):
    # Generate validator keys for the selected network

    result = button_dialog(
        title='Generating keys',
        text=(
'''
This next step will generate the keys needed to be a validator.

It will download the official eth2.0-deposit-cli binary from GitHub,
verify its SHA256 checksum, extract it and start it.

The eth2.0-deposit-cli tool is executed in an interactive way where you
have to answer a few questions. It will help you create a mnemonic from
which all your keys will be derived from. The mnemonic is the ultimate key.
It is VERY IMPORTANT to securely and privately store your mnemonic. It can
be used to recreate your validator keys and eventually withdraw your funds.

When asked how many validators you wish to run, remember that you will have
to do a 32 ETH deposit for each validator.
'''     ),
        buttons=[
            ('Generate', True),
            ('Quit', False)
        ]
    ).run()

    if not result:
        return result
    
    # Getting latest eth2.0-deposit-cli release files
    eth2_cli_gh_release_url = GITHUB_REST_API_URL + ETH2_DEPOSIT_CLI_LATEST_RELEASE
    headers = {'Accept': GITHUB_API_VERSION}
    response = httpx.get(eth2_cli_gh_release_url, headers=headers)

    if response.status_code != 200:
        # TODO: Better handling for network response issue
        return False
    
    release_json = response.json()

    if 'assets' not in release_json:
        # TODO: Better handling on unexpected response structure
        return False
    
    binary_asset = None
    checksum_asset = None

    for asset in release_json['assets']:
        if 'name' not in asset:
            continue
        if 'browser_download_url' not in asset:
            continue
    
        file_name = asset['name']
        file_url = asset['browser_download_url']

        if file_name.endswith('linux-amd64.tar.gz'):
            binary_asset = {
                'file_name': file_name,
                'file_url': file_url
            }
        elif file_name.endswith('linux-amd64.sha256'):
            checksum_asset = {
                'file_name': file_name,
                'file_url': file_url
            }

    if binary_asset is None or checksum_asset is None:
        # TODO: Better handling of missing asset in latest release
        return False
    
    # Downloading latest eth2.0-deposit-cli release files
    download_path = Path(Path.home(), 'eth2validatorwizard', 'downloads')
    download_path.mkdir(parents=True, exist_ok=True)

    binary_path = Path(download_path, binary_asset['file_name'])
    binary_hash = hashlib.sha256()

    with open(str(binary_path), 'wb') as binary_file:
        with httpx.stream('GET', binary_asset['file_url']) as http_stream:
            for data in http_stream.iter_bytes():
                binary_file.write(data)
                binary_hash.update(data)

    binary_hexdigest = binary_hash.hexdigest()

    checksum_path = Path(download_path, checksum_asset['file_name'])

    with open(str(checksum_path), 'wb') as signature_file:
        with httpx.stream('GET', checksum_asset['file_url']) as http_stream:
            for data in http_stream.iter_bytes():
                signature_file.write(data)

    # Verify SHA256 signature
    with open(str(checksum_path), 'r') as signature_file:
        if binary_hexdigest != signature_file.read(1024).strip():
            # SHA256 checksum failed
            # TODO: Better handling of failed SHA256 checksum
            return False
    
    # Extracting the eth2.0-deposit-cli binary archive
    eth2_deposit_cli_path = Path(Path.home(), 'eth2validatorwizard', 'eth2depositcli')
    eth2_deposit_cli_path.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        'tar', 'xvf', str(binary_path), '--strip-components', '2', '--directory',
        eth2_deposit_cli_path])
    
    # Remove download leftovers
    binary_path.unlink()
    checksum_path.unlink()

    # Clean potential leftover keys
    validator_keys_path = Path(eth2_deposit_cli_path, 'validator_keys')
    if validator_keys_path.exists():
        if validator_keys_path.is_dir():
            shutil.rmtree(str(validator_keys_path))
        elif validator_keys_path.is_file():
            validator_keys_path.unlink()
    
    # Launch eth2.0-deposit-cli
    eth2_deposit_cli_binary = Path(eth2_deposit_cli_path, 'deposit')
    subprocess.run([
        str(eth2_deposit_cli_binary), 'new-mnemonic', '--chain', network],
        cwd=eth2_deposit_cli_path)

    # Verify the generated keys
    deposit_data_path = None
    keystore_paths = []

    with os.scandir(validator_keys_path) as dir_it:
        for entry in dir_it:
            if not entry.name.startswith('.') and entry.is_file():
                if entry.name.startswith('deposit_data'):
                    deposit_data_path = entry.path
                elif entry.name.startswith('keystore'):
                    keystore_paths.append(entry.path)
    
    if deposit_data_path is None or len(keystore_paths) == 0:
        # No key generated
        # TODO: Better handling of no key(s) generated
        return False

    return {
        'validator_keys_path': str(validator_keys_path),
        'deposit_data_path': deposit_data_path,
        'keystore_paths': keystore_paths
    }

def install_lighthouse_validator(network, keys):
    # Import keystore(s) and configure the Lighthouse validator client

    result = button_dialog(
        title='Lighthouse validator client',
        text=(
'''
This next step will import your keystore(s) to be used with the Lighthouse
validator client and it will configure the Lighthouse validator client.

During the importation process, you will be asked to enter the password
you typed during the key(s) generation step. It is not your mnemonic.

It will create a systemd service that will automatically start the
Lighthouse validator client on reboot or if it crashes.
'''     ),
        buttons=[
            ('Configure', True),
            ('Quit', False)
        ]
    ).run()

    if not result:
        return result
    
    # Setup Lighthouse validator client user and directory
    subprocess.run([
        'useradd', '--no-create-home', '--shell', '/bin/false', 'lighthousevalidator'])
    subprocess.run([
        'mkdir', '-p', '/var/lib/lighthouse/validators'])
    subprocess.run([
        'chown', '-R', 'lighthousevalidator:lighthousevalidator', '/var/lib/lighthouse/validators'])
    subprocess.run([
        'chmod', '700', '/var/lib/lighthouse/validators'])
    
    # Import keystore(s)
    subprocess.run([
        '/usr/local/bin/lighthouse', '--network', network, 'account', 'validator', 'import',
        '--directory', keys['validator_keys_path'], '--datadir', '/var/lib/lighthouse'])

    # TODO: Check for correct keystore(s) import

    # Make sure validators directory is owned by the right user/group
    subprocess.run([
        'chown', '-R', 'lighthousevalidator:lighthousevalidator', '/var/lib/lighthouse/validators'])

    # Setup Lighthouse validator client systemd service
    with open('/etc/systemd/system/lighthousevalidator.service', 'w') as service_file:
        service_file.write(LIGHTHOUSE_VC_SERVICE_DEFINITION[network])
    subprocess.run([
        'systemctl', 'daemon-reload'])
    subprocess.run([
        'systemctl', 'start', 'lighthousevalidator'])
    subprocess.run([
        'systemctl', 'enable', 'lighthousevalidator'])

    return True