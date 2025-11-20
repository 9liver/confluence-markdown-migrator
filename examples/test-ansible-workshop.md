Trainer: Osman Omer

Attendees: Björn Gräbe, Erwin Schmidt (more attendess possible)

# Goals

| Goal  Notes  Status 
| --- | --- | --- |
| Build a fast solution for information gathering and analysis of the whole AIX landscape of Oediv.    DONE 
| Local yum repositorie  `yum install createrepo`<br>`cd to folder`<br>`createrepo noarch (creates Folder repodata)`<br>`/opt/freeware/etc/yum/yum.conf`<br>`[AIX_Toolbox_noarch_local]`<br>`name=AIX noarch local repository`<br>`baseurl=file:///tmp/repotest/noarch`<br>`enabled=1 #0 to disable it`<br>`gpgcheck=0`  DONE 
| Execute commands on all AIX-Machine  `ansible all -m shell -a 'ifconfig -a'`<br>`ansible all -m shell -a 'hostname' -o`  DONE 
| Build Groups for executing and changing things on different categories: WPARs/LPARs, test system/production systems, VIOS/none VIOS  `/etc/ansible/hosts`<br>`[testclients]`<br>`10.234.100.10`<br>`10.234.100.11`  DONE 
| Install iFixes on AIX Systems "in Waves"    DONE 
| Install Software and update on AIX Systems "in Waves"  Ansible Module: installp<br>`- name: Install Java`<br>`  installp:`<br>`  accept_license: yes`<br>`  repository_path: /ansible-mnt/aix/Java8`<br>`  name: Java8_64.jre`<br>`  state: present`  DONE 
| Maintain a system list consistent with reality  Has to be integratet in the install process AIX  DONE 
| Change files on multipe AIX-Systems or on the whole AIx enviroment  `---`<br>`- name: Change 02sapbasis to new blabla`<br>`  hosts: all`<br>`  tasks:`<br>`  - name: Changing file`<br>`    replace:`<br>`      path: /etc/sudo.d/02sapbasis`<br>`      regexp: '/int/sappatch/'`<br>`      replace: '/int/software/sappatch/'`<br>`      backup: yes`  DONE 
| Create Users  `module user or just use shell`  DONE 
| List Users  `module Shell`<br>`shell: lsuser <username>`  DONE 
| Verbose success list  `ansible-playbook -v(vv) playbook`  DONE 
| Set file permission and owners  `---`<br>`- name: Change file attributes`<br>`  hosts: all`<br>`  tasks:`<br>`  - name: Change file attributes`<br>`    file:`<br>`      path: /tmp/filetest.txt`<br>`      owner: graebebsa`<br>`      group: staff`<br>`      mode: 0777`  DONE 
| Retrieve file permissions  `Script`  DONE 
| Execute Scripts  `---`<br>`- name: Test Script Module`<br>`  hosts: all`<br>`  tasks:`<br>`  - name: Execue Script`<br>`    script: /tmp/ansible_workshop/playbooks/testscript.sh`<br>`Ansible with pipe the output the stdout on the master in oposite to ansible-playbook`  DONE 
| Test Cconnections Localy (is Port open)  `Script, with ansible (not ansible-playbook)`  DONE 
| Patterns for Playbooks?  `---`<br>`- name:  Install JAVA from NIM`<br>`  hosts: 10.234.100.11`<br>`  tasks:`<br>`  - name: Include Mount`<br>`    include: ansible_mounts.yml`<br>`   do something`<br>`  - name: Include umount`<br>`    include: ansible_umounts.yml`  DONE 
| Become Statement    DONE 
| Check for Operating Systems  `Scripts: ansible all -m shell -a "oslevel -s" -o`  DONE 
| Basic understating of roles  [https://docs.ansible.com/ansible/2.7/user_guide/playbooks_reuse_roles.html?highlight=roles&extIdCarryOver=true&sc_cid=701f2000001OH6uAAG](https://docs.ansible.com/ansible/2.7/user_guide/playbooks...)  DONE 
| with_items  `- name: Create some files`<br>`    file:`<br>`      path: "{{ item }}"`<br>`      state: touch`<br>`    with_items:`<br>`      - /ansible/file1.txt`<br>`      - /ansible/file2.txt`  DONE 
| with_file  --- <br> - name: Output files <br> hosts: all <br> tasks: <br> - name: Output files <br> # emit a debug message containing the content of each file. <br> debug: <br> msg: "{{ item }}" <br> with_file: <br> - /etc/hosts <br> #        - /ansible/file1.txt <br> #        - /ansible/file2.txt <br> <br> Files are search on the ansible controller.  DONE

# Rooms

| Mon  Tue  Wed  Thu  Fri 
| --- | --- | --- | --- | --- |
| Merkur  Merkur  Jupiter  Merkur  Merkur 
| 09:00 - ?  09:00 - ?  09:00 - ?  09:00 - ?  (09:00 - ?)

# Environment

The environment for the Ansible workshop consists of three LPARs on :

- sys-oed-125-a: 10.234.100.9 (Ansible server)
- sys-oed-126-a: 10.234.100.10 (Ansible client)
- sys-oed-127-a: 10.234.100.11(Ansible Client)

# Results by day

| Day  Results 
| --- | --- |
| Monday  [ansible-tag1.txt](/display/ICS/Ansible+Workshop?preview=%2F42974566%2F42975...)<br> Ansible is succesfully installed on sys-oed-125-a<br> installed ansible packages:<br> [https://github.com/kairoaraujo/ansible-aix-support/releases/download/0.3.1/ansible-aix-support-0.3.1.tar.gz](https://github.com/kairoaraujo/ansible-aix-support/releas...) 
| Tuesday  ansible-aix-support package: install-ansible-aix-suppoert.sh<br>Folder to find modules: /opt/free/lib/python2.7/site-packages/ansible<br>ansible-doc user (example) (Refer to this, because the online documentation is current and does not necessarly mean it is right forthe current installation<br>jumphost ist possible:<br>[https://docs.ansible.com/ansible/2.7/reference_appendices/faq.html#how-do-i-generate-crypted-passwords-for-the-user-module](https://docs.ansible.com/ansible/2.7/reference_appendices...)<br>DON'T use the mount module, it is only suitable for Linux<br>Be carefull with the aix_filesystems module. The option to remove the mount point does not work, IT ALWAYS REMOVES THE MOUNT POINT!<br>Use a seperate mount-points to for all ansible related tasks. 
| Wednesday   
| Thursday   
| Friday