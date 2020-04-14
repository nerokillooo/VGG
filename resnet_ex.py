import torch
import torch.nn as nn
from torch.hub import load_state_dict_from_url

model_urls = {
    'resnet18': 'https://download.pytorch.org/models/resnet18-5c106cde.pth',
    'resnet34': 'https://download.pytorch.org/models/resnet34-333f7ec4.pth',
    'resnet50': 'https://download.pytorch.org/models/resnet50-19c8e357.pth',
    'resnet101': 'https://download.pytorch.org/models/resnet101-5d3b4d8f.pth',
    'resnet152': 'https://download.pytorch.org/models/resnet152-b121ed2d.pth',
    'resnext50_32x4d': 'https://download.pytorch.org/models/resnext50_32x4d-7cdf4587.pth',
    'resnext101_32x8d': 'https://download.pytorch.org/models/resnext101_32x8d-8ba56ff5.pth',
    'wide_resnet50_2': 'https://download.pytorch.org/models/wide_resnet50_2-95faca4d.pth',
    'wide_resnet101_2': 'https://download.pytorch.org/models/wide_resnet101_2-32ee1156.pth',
}

def con3x3(in_planes, out_planes, stride=1, padding=1):
    #Why no bias::after Conv, there is a BN layer. Bias of BN will set be 0. So, 不用偏置参数，可以节省内存
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride, padding=padding, bias=False)
#Why need con1*1::dedimension, decrease parameters, decrease calculation; increase depth, increase model expression
def conv1x1(in_planes, out_planes, stride=1):
  return nn.Conv2d(in_planes, out_planes, kernel_size=1, stride=stride, bias=False)

# Build Block
# BasicBlock is used in ResNet layer<50
class BasicBlock(nn.Module):
    expansion = 1 # 输出通道数是plane*expansion
    
    # inplanes是输入给block的通道数，planes表示block的输出通道
    def __init__(self, inplanes, planes, stride=1, downsample=None, norm_layer=None):
        # downsample: 必须保证残差的维度与真正输出的维度相等（注意这里维度是宽高以及深度),所以需要降采样操作。
        super(BasicBlock, self).__init__()
        if norm_layer is None:
            norm_layer = nn.BatchNorm2d# 如果bn层没有自定义，就使用标准的bn层
            self.conv1 = conv3x3(inplanes, planes, stride)
            self.bn1 = norm_layer(planes)
            self.relu = nn.ReLU(inplace=True)
            self.conv2 = conv3x3(planes, planes)
            self.bn2 = norm_layer(planes)
            self.downsample = downsample
            self.stride = stride

    # execute Block
    def forward(self, x):
        identity = x # Save x

        out = self.conv1(x)# conv3*3,64d
        out = self.bn1(out)
        out = self.relu(out)# relu
        out = self.conv2(out)# conv3*3,64d
        out = self.bn2(out)

        if self.downsample is not None:
            identity = self.downsample(x)# downsample调整x的维度，F(x)+x一致才能相加

        out += identity # add x
        # Why put ReLU after addition?
        # This is just an empirical result.
        out = self.relu(out)

        return out
# BottleBlock is used in ResNet layer>50
class Bottleneck(nn.Module):
    expansion = 4# The output of the final Conv will expand 4 times

    def __init__(self, inplanes, planes, stride=1, downsample=None, norm_layer=None):
        super(Bottleneck, self).__init__()
        if norm_layer is None:
            norm_layer = nn.BatchNorm2d
    
            self.conv1 = conv1x1(inplanes, planes)
            self.bn1 = norm_layer(planes)
            self.conv2 = conv3x3(planes, planes, stride)
            self.bn2 = norm_layer(planes)
            self.conv3 = conv1x1(planes, planes * self.expansion) # 输入的channel数：planes * self.expansion
            self.bn3 = norm_layer(planes * self.expansion)
            self.relu = nn.ReLU(inplace=True)
            self.downsample = downsample
            self.stride = stride

    def forward(self, x):
        identity = x

        out = self.conv1(x)# conv1*1,d
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)# conv3*3,d
        out = self.bn2(out)
        out = self.relu(out)

        out = self.conv3(out)# conv1*1,d*4
        out = self.bn3(out)
    
        if self.downsample is not None:
           identity = self.downsample(x)

        out += identity
        out = self.relu(out)

        return out
    
# Build ResNet Model
class ResNet(nn.Module):
    def __init__(self, block, layer, num_class=1000, norm_layer=None):
        super(ResNet, self).__init__()
        if norm_layer is None:
           norm_layer = nn.BatchNorm2d
        self._norm_layer = norm_layer# 使用标准的bn层

        self.inplanes = 64# input channel number is 64

        self.conv1 = nn.Conv2d(3, self.inplanes, kernel_size=7, stride=2, padding=3, bias=False)
        self.bn1 = norm_layer(self.inplanes)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0])
        self.layer2 = self._make_layer(block, 128, layers[1], stride=2)
        self.layer3 = self._make_layer(block, 256, layers[2], stride=2)
        self.layer4 = self._make_layer(block, 512, layers[3], stride=2)
        #AdaptiveAvgPool2d()::Regardless of the size of the previous feature map, as long as it is set to (1,1), then the final feature map size is (1,1)
        self.avgpool = nn.AdaptiveAvgPool2d((1,1))  # (1,1)等于GAP
        self.fc = nn.Linear(512*block.expansion, num_class)

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

    def _make_layer(self, block, planes, blocks, stride=1):
        # 生成不同的stage/layer
        # block: block type(basic block/bottle block)
        # blocks: blocks的数量
        norm_layer = self._norm_layer
        downsample = None

        if stride != 1 or self.inplanes != planes * block.expansion:
           # 需要调整维度
           downsample = nn.Sequential(
               conv1x1(self.inplanes, planes * block.expansion, stride),  # 同时调整spatial(H x W))和channel两个方向
               norm_layer(planes * block.expansion)
           )

        layers = []
        layers.append(block(self.inplanes, planes, stride, downsample, norm_layer)) # 第一个block单独处理
        self.inplanes = planes * block.expansion  # 记录layerN的channel变化，具体请看ppt resnet表格
        for _ in range(1, blocks): # 从1开始循环，因为第一个模块前面已经单独处理
            layers.append(block(self.inplanes, planes, norm_layer=norm_layer))
        return nn.Sequential(*layers)  # 使用Sequential层组合blocks，形成stage。如果layers=[2,3,4]，那么*layers=？

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)
        
        #each ResNet has 4 stages. Every stage has several blocks
        x = self.layer1(x)# a stage
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)

        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.fc(x)

        return x
    
# Call to ResNet model
def _resnet(arch, block, layers, pretrained, progress, **kwargs):
    model = ResNet(block, layers, **kwargs)
    if pretrained:
        state_dict = load_state_dict_from_url(model_urls[arch], progress=progress)
        model.load_state_dict(state_dict)
    return model

def resnet18(pretrained=False, progress=True, **kwargs):
    r"""ResNet-18 model from
    `"Deep Residual Learning for Image Recognition" <https://arxiv.org/pdf/1512.03385.pdf>`_
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    # the number of Blocks in 4 stages is saved in list[2, 2, 2, 2]
    return _resnet('resnet18', BasicBlock, [2, 2, 2, 2], pretrained, progress, **kwargs)

def resnet50(pretrained=False, progress=True, **kwargs):
    r"""ResNet-50 model from
    `"Deep Residual Learning for Image Recognition" <https://arxiv.org/pdf/1512.03385.pdf>`_
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    return _resnet('resnet50', Bottleneck, [3, 4, 6, 3], pretrained, progress, **kwargs) 
    
        
