# Ansible lokal einrichten

Diese Anleitung beschreibt, wie unsere Ansible-Umgebung für die Entwicklung und Tests lokal eingerichtet werden kann.

> [!INFO]
> Alle Pfade in dieser Anleitung sind natürlich als persönliche Vorlieben anzusehen und frei nach belieben anzupassen :)

> [!INFO]
> Diese Anleitung setzt vorraus, dass die VDI bereits eingerichtet ist, da hier mindestens der lokale squid für den Zugriff von pip benötigt wird!

> [!INFO]
> Ab [Punkt 3](#3-ssh-keypair-einrichten) kann diese Anleitung auch verwendet werden, um Ansible auf der sys-oed-103-u zu konfigurieren

> [!INFO]
> **Changelog**
>
> 2024-10-31: Anpassung von Links und Configs an das neue GitLab

## Schritt-für-Schritt-Anleitung

1. Für diese Anleitung notwendige Pakete installieren

   ```bash
   $ sudo apt update && sudo apt install python3 python3-pip git
   ```

2. Da die Ansible Version aus den offiziellen repos zu alt ist und einige module fehlen installieren wir [Ansible über pip](https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html#pip-install)

   1. Sofern Ansible bereits über die Paketverwaltung installiert wurde:

      ```bash
      $ sudo apt remove ansible
      ```

   2. Ansible installieren

      ```bash
      $ python3 -m pip install --proxy http://127.0.0.1:3128 --user ansible
      ```

   3. Pfad zum Ansible binary bekannt machen in `~/.profile`

      **~/.profile**

      ```bash
      # set PATH so it includes user's private bin if it exists
      if [ -d "$HOME/.local/bin" ] ; then
          PATH="$HOME/.local/bin:$PATH"
      fi
      ```

      > [!NOTE]
      > Eventuell bereits in der standard `.profile` vorhanden, bitte prüfen
      >
      > `.profile` wird beim Login einmalig eingelesen. Falls `.local/bin` nicht bereits vorher existierte ist ein relogin notwendig. Da ein relogin mit Citrix so meines Wissens nicht möglich ist, wäre hier ein reboot notwendig.
      >
      > Alternativ vorerst zur Laufzeit
      >
      > ```bash
      > export PATH="$HOME/.local/bin:$PATH"
      > ```

   4. Ansible version prüfen

      ```bash
      $ ansible --version
      ```

      Zum Zeitpunkt der Doku entspricht dies:

      ```text
      ansible [core 2.16.6]
        config file = /home/OEDIV/reinersm/.ansible/ansible.cfg
        configured module search path = ['/home/OEDIV/reinersm/.ansible/plugins/modules', '/usr/share/ansible/plugins/modules']
        ansible python module location = /home/OEDIV/reinersm/.local/lib/python3.10/site-packages/ansible
        ansible collection location = /home/OEDIV/reinersm/.ansible/collections:/usr/share/ansible/collections
        executable location = /home/OEDIV/reinersm/.local/bin/ansible
        python version = 3.10.12 (main, Nov 20 2023, 15:14:05) [GCC 11.4.0] (/usr/bin/python3)
        jinja version = 3.0.3
        libyaml = True
      ```

   5. Optional: Ansible updaten

      ```bash
      $ python3 -m pip install --proxy http://127.0.0.1:3128 --upgrade --user ansible
      ```

3. Das SSH-Keypair auf der VDI und im GitLab hinterlegen {#3-ssh-keypair-einrichten}

   > [!NOTE]
   > Wenn ihr euer Schlüsselpaar über MobaXterm erzeugt habt, liegt dieses vermutlich im PuTTY-Format PPK vor und muss vorher noch in das OpenSSH Format konvertiert werden: [Hier eine Anleitung vom 2nd Level](https://confluence.oediv.lan/pages/viewpage.action?pageId=265663550)

   1. SSH-Verzeichnis erstellen

      ```bash
      $ mkdir ~/.ssh
      ```

   2. Berechtigungen setzen

      ```bash
      $ chmod 700 ~/.ssh
      ```

   3. Private-Key (und optional Public-Key) auf der VDI unter `~/.ssh/<private key filename>` ablegen

   4. Berechtigungen für Private-Key setzen

      ```bash
      $ chmod 600 ~/.ssh/<private key filename>
      ```

      > [!INFO]
      > Standard SSH Namensschemata für ssh-keys: `id_rsa, id_ecdsa, id_ecdsa_sk, id_ed25519, id_ed25519_sk` oder `id_dsa`

   5. Den eigenen Public-Key im GitLab hinterlegen: [SSH Keys · User Settings · GitLab (oediv.io)](https://gitlab.services.p.oediv.io/-/user_settings/ssh_keys)

4. Konfigurationsdateien anlegen

   1. ansible config mit nützlichen defaults. Der `remote_user` und `roles_path` ist hier anzupassen

      **~/.ansible/ansible.cfg**

      ```ini
      [defaults]
      forks = 10
      timeout = 20
      vault_password_file = $HOME/.vault_pass
      remote_user = <username>
      host_key_checking = False
      action_warnings = False
      deprecation_warnings = False
      inventory_ignore_extensions = .json
      remote_tmp = /tmp
      allow_world_readable_tmpfiles = true
      roles_path = <Pfad zum Verzeichnis der Ansible Rollen z.B. ~/workspace/git/ansible-roles/>
      ```

   2. git config mit nützlichen Aliassen. Email-Adresse und Name des Benutzers sind zu ändern (siehe auch: [Anpassungen 3rd Level Web Application Services - Michel Schweegmann](https://confluence.oediv.lan/x/0TnrB))

      **~/.gitconfig**

      ```ini
      [user]
          email = <email of user>
          name = <full name of user>
      [http]
          sslVerify = false
          proxy = http://127.0.0.1:3128
      [https]
          sslVerify = false
          proxy = http://127.0.0.1:3128
      [alias]
          br = branch
          ch = checkout
          chb = checkout -b
          co = commit
          com = commit -m
          pu = pull
          pushu = push -u origin HEAD
          st = status
      ```

   3. ssh config, um für gitlab automatisch den richtigen ssh-user zu benutzen

      **~/.ssh/config**

      ```text
      Host gitlab.services.p.oediv.io
        User git
        # Optional: falls der Name des private keys nicht dem erwarteten Standard (id_rsa, id_ecdsa, id_ecdsa_sk, id_ed25519, id_ed25519_sk oder id_dsa) entspricht
        # IdentityFile /<home path of user>/.ssh/<name of privatekey>
      ```

   4. Umgebungsvariablen für Ansible können am Ende der `.bashrc` angefügt werden

      **~/.bashrc**

      ```bash
      [...]

      ANSIBLE_CONFIG=$HOME/.ansible/ansible.cfg
      export ANSIBLE_CONFIG
      export ANSIBLE_BECOME=true
      ```

      1. Anschließend Änderungen direkt aktivieren:

         ```bash
         $ source ~/.bashrc
         ```

   5. Ansible Vault Passwort anlegen

      1. Das Passwort kann im Thycotic eingesehen werden: **Geheime Schlüssel > ICC > IOS-POC-LNX > SYSTEMS > Ansible > Ansible Vault**

      2. Abzulegen ist das Passwort hier: `~/.vault_pass`

      3. Berechtigungen setzen

         ```bash
         $ chmod 600 ~/.vault_pass
         ```

5. fertig

## Verwandte Artikel
