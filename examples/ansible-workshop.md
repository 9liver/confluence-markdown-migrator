---
confluence_page_id: '42974566'
title: Ansible Workshop
space_key: ICS
space_name: Infrastructure & Cloud Services
parent_id: '42974565'
hierarchy_depth: 0
relative_path: ansible-workshop.md
filesystem_depth: 0
labels: []
version: 11
attachments: []
attachment_count: 0
conversion_status: success
export_timestamp: '2025-11-20T12:36:44.939269Z'
---

Trainer: Osman Omer

Attendees: Björn Gräbe, Erwin Schmidt (more attendess possible)

# Goals

| Goal | Notes | Status |
| --- | --- | --- |
| Build a fast solution for information gathering and analysis of the whole AIX landscape of Oediv. |  | DONE |
| Local yum repositorie | ``` yum install createrepo cd to folder createrepo noarch (creates Folder repodata) /opt/freeware/etc/yum/yum.conf  [AIX_Toolbox_noarch_local] name=AIX noarch local repository baseurl=file:///tmp/repotest/noarch enabled=1 #0 to disable it gpgcheck=0 ``` | DONE |
| Execute commands on all AIX-Machine | ``` ansible all -m shell -a 'ifconfig -a'  ansible all -m shell -a 'hostname' -o ``` | DONE |
| Build Groups for executing and changing things on different categories: WPARs/LPARs, test system/production systems, VIOS/none VIOS | ``` /etc/ansible/hosts  [testclients] 10.234.100.10 10.234.100.11 ``` | DONE |
| Install iFixes on AIX Systems "in Waves" |  | DONE |
| Install Software and update on AIX Systems "in Waves" | Ansible Module: installp ``` - name: Install Java   installp:   accept_license: yes   repository_path: /ansible-mnt/aix/Java8   name: Java8_64.jre   state: present   ``` | DONE |
| Maintain a system list consistent with reality | Has to be integratet in the install process AIX | DONE |
| Change files on multipe AIX-Systems or on the whole AIx enviroment | ``` --- - name: Change 02sapbasis to new blabla   hosts: all   tasks:   - name: Changing file     replace:       path: /etc/sudo.d/02sapbasis       regexp: '/int/sappatch/'       replace: '/int/software/sappatch/'       backup: yes   ``` | DONE |
| Create Users | ``` module user or just use shell  ``` | DONE |
| List Users | ``` module Shell  shell: lsuser <username> ``` | DONE |
| Verbose success list | ``` ansible-playbook -v(vv) playbook ``` | DONE |
| Set file permission and owners | ``` --- - name: Change file attributes   hosts: all   tasks:   - name: Change file attributes     file:       path: /tmp/filetest.txt       owner: graebebsa       group: staff       mode: 0777 ``` | DONE |
| Retrieve file permissions | ``` Script ``` | DONE |
| Execute Scripts | ``` --- - name: Test Script Module   hosts: all   tasks:   - name: Execue Script     script: /tmp/ansible_workshop/playbooks/testscript.sh  Ansible with pipe the output the stdout on the master in oposite to ansible-playbook  ``` | DONE |
| Test Cconnections Localy (is Port open) | ``` Script, with ansible (not ansible-playbook) ``` | DONE |
| Patterns for Playbooks? | ``` --- - name:  Install JAVA from NIM   hosts: 10.234.100.11   tasks:   - name: Include Mount     include: ansible_mounts.yml     do something    - name: Include umount     include: ansible_umounts.yml ``` | DONE |
| Become Statement |  | DONE |
| Check for Operating Systems | ```  Scripts: ansible all -m shell -a "oslevel -s" -o ``` | DONE |
| Basic understating of roles | <https://docs.ansible.com/ansible/2.7/user_guide/playbooks_reuse_roles.html?highlight=roles&extIdCarryOver=true&sc_cid=701f2000001OH6uAAG> | DONE |
| with_items | ```   - name: Create some files     file:       path: "{{ item }}"       state: touch     with_items:       - /ansible/file1.txt       - /ansible/file2.txt ``` | DONE |
| with_file | --- - name: Output files   hosts: all   tasks:   - name: Output files     # emit a debug message containing the content of each file.     debug:         msg: "{{ item }}"     with_file:         - /etc/hosts #        - /ansible/file1.txt #        - /ansible/file2.txt  Files are search on the ansible controller. | DONE |


# Rooms

| Mon | Tue | Wed | Thu | Fri |
| --- | --- | --- | --- | --- |
| Merkur | Merkur | Jupiter | Merkur | Merkur |
| 09:00 - ? | 09:00 - ? | 09:00 - ? | 09:00 - ? | (09:00 - ?) |


# Environment

The environment for the Ansible workshop consists of three LPARs on :

- sys-oed-125-a: 10.234.100.9 (Ansible server)
- sys-oed-126-a: 10.234.100.10 (Ansible client)
- sys-oed-127-a: 10.234.100.11(Ansible Client)

# Results by day

| Day | Results |
| --- | --- |
| Monday | [ansible-tag1.txt](/display/ICS/Ansible+Workshop?preview=%2F42974566%2F42975276%2Fansible-tag1.txt)  Ansible is succesfully installed on sys-oed-125-a  installed ansible packages:  <https://github.com/kairoaraujo/ansible-aix-support/releases/download/0.3.1/ansible-aix-support-0.3.1.tar.gz> |
| Tuesday | ansible-aix-support package: install-ansible-aix-suppoert.sh  Folder to find modules: /opt/free/lib/python2.7/site-packages/ansible  ansible-doc user (example) (Refer to this, because the online documentation is current and does not necessarly mean it is right forthe current installation  jumphost ist possible:  <https://docs.ansible.com/ansible/2.7/reference_appendices/faq.html#how-do-i-generate-crypted-passwords-for-the-user-module>    DON'T use the mount module, it is only suitable for Linux  Be carefull with the aix_filesystems module. The option to remove the mount point does not work, IT ALWAYS REMOVES THE MOUNT POINT!  Use a seperate mount-points to for all ansible related tasks. |
| Wednesday |  |
| Thursday |  |
| Friday |  |

