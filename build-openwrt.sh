#!/bin/bash

mkdir -p ~/workshop/R4A/build
sudo docker run --name openwrt -it -v /home/axe/workshop/R4A/build:/build ubuntu:latest
sudo docker run --name openwrt -it --rm \
  -v /home/axe/workshop/R4A/build:/build huhongjun/openwrt:build

export https_proxy=http://10.0.0.204:20172
export http_proxy=http://10.0.0.204:20172
git config --global http.proxy http://10.0.0.204:20172
git config --global https.proxy http://10.0.0.204:20172

mv ~/.subversion/servers ~/.subversion/servers-bak
echo '''
[global]
http-proxy-host = ip.add.re.ss
http-proxy-port = 3128
http-proxy-compression = no
''' >~/.subversion/servers

# 环境准备
apt install -y git subversion vim python3 python3-pip
apt-get update
apt-get -y install gcc-multilib gettext libncurses5-dev
apt-get clean
apt install -y rsync gawk unzip wget file # feed update required

cd /build && git clone https://github.com/huhongjun/ActionBuild-openwrt.git
cd /build/ActionBuild-openwrt

pip3 install -r extra-files/requirements-transit.txt

# 读取配置
export MODEL_NAME='xiaomi-4a-gigabit-v2'
export LOGIN_IP='10.0.0.1'
export LOGIN_PWD='root1234'
export DEPLOYDIR='preset-openwrt'
export TEMP_PREFIX='temp'

# 以preset-openwrt下的文件为模板修改生成临时文件: clone.sh, modify.sh, release
python3 extra-files/transit.py

# 下载源码与插件
CLONE_SH=${DEPLOYDIR}/${TEMP_PREFIX}.clone.sh
sed -i '/SWITCH_TAG_FLAG=/ s/false/true/' $CLONE_SH
chmod +x $CLONE_SH
$CLONE_SH # openwrt仓库下文件移动到当前目录

# 升级feeds
./scripts/feeds update -a
./scripts/feeds install -a

# 修改配置
MODIFY_SH=${DEPLOYDIR}/${TEMP_PREFIX}.modify.sh
chmod +x $MODIFY_SH
$MODIFY_SH

# 生成.config文件
DOT_CONFIG=${DEPLOYDIR}/${TEMP_PREFIX}.config
mv $DOT_CONFIG .config
make defconfig
# 下载编译资源
make download -j8 || make download -j1 V=s
# 编译
make -j$(nproc) || make -j1 V=s

# 整理固件目录
mkdir -p collected_firmware/packages
rm -rf $(find bin/targets/ -type d -name 'packages')
cp $(find bin/targets/ -type f) collected_firmware
cp $(find bin/packages/ -type f -name '*.ipk') collected_firmware/packages
cd collected_firmware
zip -r allfiles.zip *
cd packages
zip -r ../packages.zip *
