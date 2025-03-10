#!/usr/bin/python3
import os
import sys
import glob
import shutil
import subprocess


import toml


sys.path.append(os.path.dirname(os.path.dirname(__file__)) + '/extra-files')
from tools import simplify, routine_cmd
from tools.crypt import crypt_root


# 获取编号
def get_serial(directory: str) -> str:
    if (total := len(glob.glob(f'{directory}/*clone.sh'))) == 0:
        number = '1'
    else:
        if os.getenv('OVERWRITE_LAST') == 'true':
            number = str(total)
        elif (os1 := os.getenv('OVERWRITE_SPEC')) != '':
            number = str(os1)
        else:
            number = str(total + 1)
    return number


# 按链接提取应用名
def extract_app_name(links: list) -> list:
    apps = []
    for link in links:
        apps += [f'* {link.split("@")[0].split("/")[-1].rstrip(".git")}\n']
    return apps


# 按链接生成git clone命令
def produce_git_command(link: str, isbase=False) -> str:
    path = ''
    link = link.strip().rstrip('@')
    # 0个@
    if '@' not in (url := link):
        command = f'git clone --depth 1 {url}'
    else:
        segment = link.split('@')
        url = segment[0]
        # 1个@
        if link.count('@') == 1:
            branch = segment[1]
            command = f'git clone --depth 1 -b {branch} {url}'
        # 2个@
        else:
            if segment[1] == '':
                path = segment[2]
                command = f'git clone --depth 1 {url} {path}'
            else:
                branch = segment[1]
                path = segment[2]
                command = f'git clone --depth 1 -b {branch} {url} {path}'
    if isbase:
        if path != '':
            path = path.rstrip('/')
            command += f' && mv ./{path}/* ./'
        else:
            command += f' openwrt && mv ./openwrt/* ./'
    return command


# 按链接生成svn命令
def produce_svn_command(link: str) -> str:
    link = link.strip().rstrip('@')
    # 0个@
    if '@' not in (url := link):
        command = f'svn export {url}'
    # 1个@
    else:
        segment = link.split('@')
        url = segment[0]
        path = segment[1]
        command = f'svn export {url} {path}'
    return command


# 生成模板化配置文件
def produce_conf(data: dict, prefix: str) -> bool:
    # 生成clone.sh
    basecommands = produce_git_command(ba := data['base'], True) + '\n'
    appcommands = []
    try:
        if data['git_app'] == '':
            raise KeyError('值不能为空')
        for link in data['git_app']:
            appcommands += [f'{produce_git_command(link)}\n']
        ga = True
    except KeyError:
        ga = False
    try:
        if data['svn_app'] == '':
            raise KeyError('值不能为空')
        for link in data['svn_app']:
            appcommands += [f'{produce_svn_command(link)}\n']
        sa = True
    except KeyError:
        sa = False
    dla = []
    if ga or sa:
        try:
            if data['app_path'] == '':
                raise KeyError('值不能为空')
            if (path := data["app_path"]).startswith('package/') or path == 'package':
                pass
            else:
                print('app_path未在package目录内')
                sys.exit()
            dla = [
                '\n# download app codes\n',
                f'mkdir -p {path} && cd {path}\n'
                ]
        except KeyError:
            print('app源已存在，但缺少app_path')
            sys.exit()
    text1 = [
        '#!/bin/sh\n',
        '\n# download base code\n',
        basecommands
    ] + dla
    text1 += appcommands
    with open(prefix + '.clone.sh', 'w') as f:
        f.writelines(text1)
    # 生成modify.sh
    text2 = [
        '#!/bin/sh\n',
        '\n# modify login IP\n'
    ]
    try:
        if data['login_ip'] == '':
            raise KeyError('值不能为空')
        text2.append(f'sed -i \'s/192.168.1.1/{data["login_ip"]}/g\' package/base-files/files/bin/config_generate\n')
        li = True
    except KeyError:
        text2.append('# sed -i \'s/192.168.1.1/192.168.51.1/g\' package/base-files/files/bin/config_generate\n')
        li = False
    text2.append('\n# modify login password\n')
    n = text2.index('\n# modify login password\n')
    try:
        if data['login_pwd'] == '':
            raise KeyError('值不能为空')
        text2.append(f"sed -i '/root/c{crypt_root(data['login_pwd'])}' package/base-files/files/etc/shadow\n")
        text2[n] = text2[n].replace('password', f'password to {data["login_pwd"]}')
        lp = True
    except KeyError:
        text2.append(f"# sed -i '/root/c{crypt_root('888888')}' package/base-files/files/etc/shadow\n")
        text2[n] = text2[n].replace('password', 'password to 888888')
        lp = False
    if 'openwrt/openwrt' in ba:
        text2 += [
            '\n# turn on wireless\n',
            'mkdir -p files/etc/uci-defaults\n',
            'cp preset-openwrt/uci-scripts/17_wireless files/etc/uci-defaults/\n',
            '\n# modify default package(s)\n',
            "sed -i 's/dnsmasq/dnsmasq-full/g' include/target.mk\n"
        ]
        offi = True
    else:
        offi = False
    with open(prefix + '.modify.sh', 'w') as f:
        f.writelines(text2)
    # 生成.config
    text3 = [
        f'CONFIG_TARGET_{(t1 := data["board"])}=y\n',
        f'CONFIG_TARGET_{t1}_{(t2 := data["subtarget"])}=y\n',
        f'CONFIG_TARGET_{t1}_{t2}_DEVICE_{(t3 := data["device"])}=y\n'
    ]
    if offi:
        extra_t = [
            '# Collections\n',
            'CONFIG_PACKAGE_luci=y\n',
            '\n# Translations\n',
            'CONFIG_LUCI_LANG_zh_Hans=y\n'
        ]
        text3 += extra_t
    with open(prefix + '.config', 'w') as f:
        f.writelines(text3)
    # 生成release.md
    text4 = [
        f'## {data["base_name"]} for {data["device_name"]}\n',
        f'\nversion：{data["base_version"]}\n',
        '\nlogin info：\n'
    ]
    if li:
        text4.insert(3, f'* IP {data["login_ip"]}\n')
    else:
        text4.insert(3, '* IP default\n')
    if lp:
        text4.insert(4, f'* Password {data["login_pwd"]}\n')
    else:
        text4.insert(4, '* Password default\n')
    if ga or sa:
        text4.append('\napplications：\n')
        if ga:
            text4 += extract_app_name(data['git_app'])
        if sa:
            text4 += extract_app_name(data['svn_app'])
    with open(prefix + '.release.md', 'w') as f:
        f.writelines(text4)
    return extra_t


def main():
    destdir = (rp1 := os.getenv('REPO_PATH').rstrip('/')) + '/' + (dd1 := os.getenv('DEPLOYDIR').rstrip('/'))
    ba1 = f'{destdir}/backups'
    wf1 = f'{rp1}/.github/workflows'
    if os.getenv('DELETE_ALL') == 'true':
        if dd1 != 'templet':
            if (len(glob.glob(f'{destdir}/*clone.sh'))) > 0:
                shutil.rmtree(destdir, ignore_errors=True)
            else:
                sys.exit()
        else:
            shutil.rmtree(ba1, ignore_errors=True)
            for item in glob.glob(f'{destdir}/[0-9].*'):
                os.remove(item)
        for item in glob.glob(f'{wf1}/{dd1}-[0-9]*'):
            os.remove(item)
        sys.exit()
    if (ds1 := os.getenv('DELETE_SPEC')) != '':
        ds1 = ds1.replace(' ', '').rstrip(',').split(',')
        for root, dirs, files in os.walk(destdir):
            for name in files:
                for serial in ds1:
                    if name.startswith(serial + '.'):
                        os.remove(os.path.join(root, name))
                        break
        for serial in ds1:
            for item in glob.glob(f'{wf1}/{dd1}-{serial}*'):
                os.remove(item)
        sys.exit()
    os.makedirs(ba1, exist_ok=True)
    serial = get_serial(destdir)
    initfile = rp1 + '/' + os.getenv('INITFILE')
    with open(initfile) as f:
        extra_t = produce_conf(tl1 := toml.load(f), serial)
    routine_cmd.gen_dot_config(serial + '.clone.sh', serial + '.config')
    simplify.simplify_config(serial + '.config', remain_text=extra_t)
    # 移动文件到目标文件夹，准备commit
    if os.getenv('OVERWRITE_LAST') == 'true':
        for item in glob.glob(f'{wf1}/{dd1}-{serial}*'):
            os.remove(item)
    for item in glob.glob(serial + '*'):
        if item.endswith('config.fullbak'):
            shutil.move(item, f'{ba1}/{item}')
        else:
            shutil.move(item, f'{destdir}/{item}')
    shutil.copyfile(f'{rp1}/templet/build.yml', by1 := f"{wf1}/{dd1}-{serial}-{tl1['device_name'].replace(' ', '-')}.yml")
    subprocess.run(f"sed -i 's/name: xxxxxx/name: {dd1} {tl1['device_name']}/' {by1}", shell=True)
    subprocess.run(f"sed -i 's/SERIAL_NU: xxxxxx/SERIAL_NU: {serial}/' {by1}", shell=True)
    subprocess.run(f"sed -i 's/DEPLOYDIR: xxxxxx/DEPLOYDIR: {dd1}/' {by1}", shell=True)


if __name__ == '__main__':
    main()
