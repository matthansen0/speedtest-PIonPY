targetScope = 'resourceGroup'

@description('Azure region for the benchmark cluster. Defaults to Central US.')
param location string = 'centralus'

@description('Name prefix used for all created resources.')
param namePrefix string = 'pionpy'

@description('Linux administrator username used on both VMs.')
param adminUsername string = 'azureuser'

@description('Password for the Linux administrator account used through Azure Bastion.')
@secure()
param adminPassword string

var vmDefinitions = [
  {
    name: '${namePrefix}-intel'
    size: 'Standard_D2s_v5'
  }
  {
    name: '${namePrefix}-arm'
    size: 'Standard_D2ps_v6'
  }
]
var vnetName = '${namePrefix}-vnet'
var vmSubnetName = 'vm-subnet'
var bastionSubnetName = 'AzureBastionSubnet'
var bastionName = '${namePrefix}-bastion'
var bastionPublicIpName = '${namePrefix}-bastion-pip'
var vmNames = [for vm in vmDefinitions: vm.name]

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.0.0.0/16'
      ]
    }
    subnets: [
      {
        name: vmSubnetName
        properties: {
          addressPrefix: '10.0.0.0/24'
        }
      }
      {
        name: bastionSubnetName
        properties: {
          addressPrefix: '10.0.1.0/26'
        }
      }
    ]
  }
}

resource vmSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-09-01' existing = {
  name: vmSubnetName
  parent: vnet
}

resource bastionSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-09-01' existing = {
  name: bastionSubnetName
  parent: vnet
}

resource bastionPublicIp 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: bastionPublicIpName
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource bastion 'Microsoft.Network/bastionHosts@2023-09-01' = {
  name: bastionName
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'bastion-ipconfig'
        properties: {
          subnet: {
            id: bastionSubnet.id
          }
          publicIPAddress: {
            id: bastionPublicIp.id
          }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
    ]
  }
}

resource vmNics 'Microsoft.Network/networkInterfaces@2023-09-01' = [for vmName in vmNames: {
  name: '${vmName}-nic'
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: vmSubnet.id
          }
          privateIPAllocationMethod: 'Dynamic'
          primary: true
        }
      }
    ]
    enableAcceleratedNetworking: true
  }
}]

resource vms 'Microsoft.Compute/virtualMachines@2023-09-01' = [for (vm, index) in vmDefinitions: {
  name: vm.name
  location: location
  properties: {
    hardwareProfile: {
      vmSize: vm.size
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: '0001-com-ubuntu-server-jammy'
        sku: vm.size == 'Standard_D2ps_v6' ? '22_04-lts-arm64' : '22_04-lts-gen2'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'Standard_LRS'
        }
      }
    }
    osProfile: {
      computerName: vm.name
      adminUsername: adminUsername
      adminPassword: adminPassword
      linuxConfiguration: {
        disablePasswordAuthentication: false
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: vmNics[index].id
        }
      ]
    }
  }
}]

output location string = location
output resourceGroupName string = resourceGroup().name
output vnetName string = vnet.name
output vmNames array = vmNames
output vmOneName string = vmNames[0]
output vmTwoName string = vmNames[1]
output vmUserName string = adminUsername
output bastionName string = bastion.name
output bastionPublicIp string = bastionPublicIp.properties.ipAddress
output vmPrivateIps array = [for (vmName, index) in vmNames: vmNics[index].properties.ipConfigurations[0].properties.privateIPAddress]
