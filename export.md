Diese Anleitung beschreibt, wie unsere Ansible-Umgebung für die Entwicklung und Tests lokal eingerichtet werden kann.

Alle Pfade in dieser Anleitung sind natürlich als persönliche Vorlieben anzusehen und frei nach belieben anzupassen
!(smile)

Diese Anleitung setzt vorraus, dass die VDI bereits eingerichtet ist, da hier mindestens der lokale squid für den
Zugriff von pip benötigt wird!

Ab [Punkt 3](https://confluence.oediv.lan/pages/viewpage.action?pageId=244744731) kann diese Anleitung auch verwendet
werden, um Ansible auf der sys-oed-103-u zu konfigurieren

Changelog

2024-10-31: Anpassung von Links und Configs an das neue GitLab

## Schritt-für-Schritt-Anleitung

1. Für diese Anleitung notwendige Pakete installieren
2. Da die Ansible Version aus den offiziellen repos zu alt ist und einige module fehlen installieren wir [Ansible über
pip](https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html#pip-install)\n        i. Sofern Ansible bereits über die Paketverwaltung installiert wurde:``` ```
        ii. Ansible installieren
        iii. Pfad zum Ansible binary bekannt machen in `~/.profile`\n\n> [!warning]
> [!info] 
> `.profile` wird beim Login einmalig eingelesen. Falls `.local/bin` nicht bereits vorher existierte ist ein relogin
> notwendig. Da ein relogin mit Citrix so meines Wissens nicht möglich ist, wäre hier ein reboot notwendig.
> 
> Alternativ vorerst zur Laufzeit
> 
> ```bash
> export PATH="$HOME/.local/bin:$PATH"
> ```

        iv. Ansible version prüfen\n\nZum Zeitpunkt der Doku entspricht dies:
        v. Optional: Ansible updaten

3. Das SSH-Keypair auf der VDI und im GitLab hinterlegen<a id="Ansiblelokaleinrichten-3"></a>\n\nWenn ihr euer Schlüsselpaar über MobaXterm erzeugt habt, liegt dieses vermutlich im PuTTY-Format PPK vor und muss vorher
noch in das OpenSSH Format konvertiert werden: [Hier eine Anleitung vom 2nd
Level](https://confluence.oediv.lan/pages/viewpage.action?pageId=265663550)\n        i.
        ii.
        iii. Private-Key (und optional Public-Key) auf der VDI unter\n\n`~/.ssh/<private key filename>`\n\nablegen
        iv. > [!info]
> Standard SSH Namensschemata für ssh-keys:`id_rsa, id_ecdsa, id_ecdsa_sk, id_ed25519, id_ed25519_sk`oder`id_dsa`
        v. Den eigenen Public-Key im GitLab hinterlegen: [SSH Keys · User Settings · GitLab
(oediv.io)](https://gitlab.services.p.oediv.io/-/user_settings/ssh_keys)

4. Konfigurationsdateien anlegen\n        i. ansible config mit nützlichen defaults. Der `remote_user` und `roles_path` ist hier anzupassen
        ii. git config mit nützlichen Aliassen. Email-Adresse und Name des Benutzers sind zu ändern (siehe auch: [Anpassungen 3rd
Level Web Application Services - Michel Schweegmann](https://confluence.oediv.lan/x/0TnrB))
        iii. ssh config, um für gitlab automatisch den richtigen ssh-user zu benutzen
        iv. Umgebungsvariablen für Ansible können am Ende der `.bashrc `angefügt werden\n                i. Anschließend Änderungen direkt aktivieren:`
`

        v. Ansible Vault Passwort anlegen\n                i. Das Passwort kann im Thycotic eingesehen werden:\n\n**Geheime Schlüssel > ICC > IOS-POC-LNX > SYSTEMS > Ansible > Ansible Vault**
                ii. Abzulegen ist das Passwort hier:\n\n`~/.vault_pass`
                iii.

5. fertig

## Verwandte Artikel

- [Ansible lokal einrichten](/display/ICS/Ansible+lokal+einrichten)
- [Ansible Playbooks / Storage Anwendungsfälle](/pages/viewpage.action?pageId=61834691)