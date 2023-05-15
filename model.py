import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

class Model():
    def __init__(self, model_name, num_gpus = 1):
        # Check if CUDA is available, set the device accordingly
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        if model_name == 'zigzag_resnet':
            # Create a ZigZag_ResNet model with 13 BasicBlocks and 2 output classes
            self.model = ZigZag_ResNet(BasicBlock, [1]*13, num_classes=2).to(self.device)
            
            # Define the CrossEntropyLoss criterion for classification
            self.criterion = nn.CrossEntropyLoss()
            
            # Create an SGD optimizer with learning rate 0.001, momentum 0.8, weight decay 0.0005, and Nesterov momentum
            self.optimizer = torch.optim.SGD(self.model.parameters(), 0.001, momentum=0.8, weight_decay=0.0005, nesterov=True)
            
            # Create a ZigZagLROnPlateauRestarts scheduler with mode 'max', initial LR 0.001,
            # up factor 0.3, down factor 0.5, up patience 1, down patience 1, restart after 30 epochs, and verbose output
            self.scheduler = ZigZagLROnPlateauRestarts(self.optimizer, mode='max', lr=0.001,
                                                    up_factor=0.3, down_factor=0.5,
                                                    up_patience=1, down_patience=1,
                                                    restart_after=30, verbose=True)
        elif model_name == 'googlenet':
            # Create a GoogLeNet model
            self.model = GoogLeNet().to(self.device)
            
            # Define the CrossEntropyLoss criterion for classification
            self.criterion = nn.CrossEntropyLoss()
            
            # Create an SGD optimizer with learning rate 0.05 * 4, momentum 0.8, weight decay 0.0005, and Nesterov momentum
            self.optimizer = torch.optim.SGD(self.model.parameters(), 0.05 * 4, momentum=0.8, weight_decay=0.0005, nesterov=True)
            
            # Create a ReduceLROnPlateau scheduler with mode 'min' and patience 2
            self.scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(self.optimizer, 'min', patience=2)

        # For Utilizing Multiple GPUs
        if num_gpus != 1:
            device_ids=[0, 1]
            self.model = torch.nn.DataParallel(self.model, device_ids=list(range(num_gpus)))
    
    def train(self, num_epochs, train_loader, val_loader):
        train_losses_ = []  # List to store training losses for each epoch
        train_accuracies_ = []  # List to store training accuracies for each epoch
        valid_losses_ = []  # List to store validation losses for each epoch
        valid_accuracies_ = []  # List to store validation accuracies for each epoch
        
        for epoch in range(num_epochs):
            print(f"\n\tEpoch: {epoch+1}/{num_epochs}")
            
            # Perform training and validation for the current epoch
            train_loss, train_accuracy, val_loss, val_accuracy = self.train_val(train_loader, val_loader)
            
            # Append the results to the respective lists
            train_losses_.append(train_loss)
            train_accuracies_.append(train_accuracy)
            valid_losses_.append(val_loss)
            valid_accuracies_.append(val_accuracy)
            
            # Print the training and validation metrics for the current epoch
            print(f"\tTraining Loss: {round(train_loss, 4)}; Training Accuracy: {round(train_accuracy*100, 4)}%")
            print(f"\tValidation Loss: {round(val_loss, 4)}; Validation Accuracy: {round(val_accuracy*100, 4)}%")

    def train_val(self, train_loader, val_loader):
        self.model.train()  # Set the model in training mode
        train_loss = 0  # Variable to store the cumulative training loss
        correct = 0  # Variable to store the number of correct predictions
        total = 0  # Variable to store the total number of samples
        
        for i, data in enumerate(train_loader, 0):
            image, label = data
            image = image.to(self.device)
            label = label.to(self.device)
            
            self.optimizer.zero_grad()  # Clear gradients from the previous iteration
            
            output = self.model(image)  # Forward pass
            loss = self.criterion(output, label)  # Calculate the loss
            
            train_loss += loss.item()  # Accumulate the training loss
            
            pred = torch.max(output.data, 1)[1]  # Get the predicted labels
            cur_correct = (pred == label).sum().item()  # Count the number of correct predictions in the current batch
            cur_loss = loss.item()  # Get the loss value as a scalar
            
            loss.backward()  # Backpropagation
            
            self.optimizer.step()  # Update the model parameters based on the gradients
            
            total += label.size(0)  # Accumulate the total number of samples
            correct += cur_correct  # Accumulate the number of correct predictions
            train_loss += cur_loss  # Accumulate the training loss

        train_accuracy = correct / total  # Calculate the training accuracy
        train_loss = train_loss / len(train_loader)  # Calculate the average training loss
        
        valid_loss, valid_accuracy = self.test(val_loader)  # Perform validation
        
        self.scheduler.step(valid_accuracy)  # Adjust the learning rate based on validation accuracy
        
        return train_loss, train_accuracy, valid_loss, valid_accuracy


    def test(self, dataloader):
        self.model.eval()  # Set the model in evaluation mode
        test_loss = 0  # Variable to store the cumulative test loss
        correct = 0  # Variable to store the number of correct predictions
        total = 0  # Variable to store the total number of samples
        
        for i, data in enumerate(dataloader, 0):
            image, label = data
            image = image.to(self.device)
            label = label.to(self.device)
            
            output = self.model(image)  # Forward pass
            loss = self.criterion(output, label)  # Calculate the loss
            
            pred = torch.max(output.data, 1)[1]  # Get the predicted labels
            cur_correct = (pred == label).sum().item()  # Count the number of correct predictions in the current batch
            cur_loss = loss.item()  # Get the loss value as a scalar
            
            total += label.size(0)  # Accumulate the total number of samples
            correct += cur_correct  # Accumulate the number of correct predictions
            test_loss += cur_loss  # Accumulate the test loss

        accuracy = correct / total  # Calculate the test accuracy
        test_loss = test_loss / len(dataloader)  # Calculate the average test loss

        return test_loss, accuracy


class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, in_planes, planes, stride=1):
        super(BasicBlock, self).__init__()
        self.conv1 = nn.Conv2d(
            in_planes, planes, kernel_size=3, stride=stride, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3,
                                stride=1, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(planes)

        self.shortcut = nn.Sequential()
        if stride != 1 or in_planes != self.expansion*planes:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_planes, self.expansion*planes,
                            kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(self.expansion*planes)
            )

    def forward(self, x):
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out += self.shortcut(x)
        out = F.relu(out)
        return out

class ZigZag_ResNet(nn.Module):
    def __init__(self, block, num_blocks, num_classes=2):
        super(ZigZag_ResNet, self).__init__()
        self.in_planes = 64

        self.conv1 = nn.Conv2d(3, 64, kernel_size=3,
                                stride=1, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.layer1 = self._make_layer(block, 64, num_blocks[0], stride=1)
        self.layer2 = self._make_layer(block, 128, num_blocks[1], stride=2)
        self.layer3 = self._make_layer(block, 256, num_blocks[2], stride=2)
        self.layer4 = self._make_layer(block, 512, num_blocks[3], stride=2)
        self.layer5 = self._make_layer(block, 1024, num_blocks[4], stride=2)
        self.layer6 = self._make_layer(block, 512, num_blocks[5], stride=2)
        self.layer7 = self._make_layer(block, 256, num_blocks[6], stride=2)
        self.layer8 = self._make_layer(block, 128, num_blocks[7], stride=2)
        self.layer9 = self._make_layer(block, 64, num_blocks[8], stride=2)
        self.layer10 = self._make_layer(block, 128, num_blocks[9], stride=2)
        self.layer11 = self._make_layer(block, 256, num_blocks[10], stride=2)
        self.layer12 = self._make_layer(block, 512, num_blocks[11], stride=2)
        self.layer13 = self._make_layer(block, 1024, num_blocks[12], stride=2)
        self.linear = nn.Linear(1024*block.expansion, num_classes)

    def _make_layer(self, block, planes, num_blocks, stride):
        strides = [stride] + [1]*(num_blocks-1)
        layers = []
        for stride in strides:
            layers.append(block(self.in_planes, planes, stride))
            self.in_planes = planes * block.expansion
        return nn.Sequential(*layers)

    def forward(self, x):
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.layer1(out)
        out = self.layer2(out)
        out = self.layer3(out)
        out = self.layer4(out)
        out = self.layer5(out)
        out = self.layer6(out)
        out = self.layer7(out)
        out = self.layer8(out)
        out = self.layer9(out)
        out = self.layer10(out)
        out = self.layer11(out)
        out = self.layer12(out)
        out = self.layer13(out)
        out = out.view(out.size(0), -1)
        out = self.linear(out)
        return out
   
class Inception(nn.Module):
    def __init__(self, in_planes, n1x1, n3x3red, n3x3, n5x5red, n5x5, pool_planes):
        super(Inception, self).__init__()
        # 1x1 conv branch
        self.b1 = nn.Sequential(
            nn.Conv2d(in_planes, n1x1, kernel_size=1),
            nn.BatchNorm2d(n1x1),
            nn.ReLU(True),
        )

        # 1x1 conv -> 3x3 conv branch
        self.b2 = nn.Sequential(
            nn.Conv2d(in_planes, n3x3red, kernel_size=1),
            nn.BatchNorm2d(n3x3red),
            nn.ReLU(True),
            nn.Conv2d(n3x3red, n3x3, kernel_size=3, padding=1),
            nn.BatchNorm2d(n3x3),
            nn.ReLU(True),
        )

        # 1x1 conv -> 5x5 conv branch
        self.b3 = nn.Sequential(
            nn.Conv2d(in_planes, n5x5red, kernel_size=1),
            nn.BatchNorm2d(n5x5red),
            nn.ReLU(True),
            nn.Conv2d(n5x5red, n5x5, kernel_size=3, padding=1),
            nn.BatchNorm2d(n5x5),
            nn.ReLU(True),
            nn.Conv2d(n5x5, n5x5, kernel_size=3, padding=1),
            nn.BatchNorm2d(n5x5),
            nn.ReLU(True),
        )

        # 3x3 pool -> 1x1 conv branch
        self.b4 = nn.Sequential(
            nn.MaxPool2d(3, stride=1, padding=1),
            nn.Conv2d(in_planes, pool_planes, kernel_size=1),
            nn.BatchNorm2d(pool_planes),
            nn.ReLU(True),
        )

    def forward(self, x):
        y1 = self.b1(x)
        y2 = self.b2(x)
        y3 = self.b3(x)
        y4 = self.b4(x)
        return torch.cat([y1,y2,y3,y4], 1)


class GoogLeNet(nn.Module):
    def __init__(self):
        super(GoogLeNet, self).__init__()
        self.pre_layers = nn.Sequential(
            nn.Conv2d(3, 192, kernel_size=3, padding=1),
            nn.BatchNorm2d(192),
            nn.ReLU(True),
        )

        self.a3 = Inception(192,  64,  96, 128, 16, 32, 32)
        self.b3 = Inception(256, 128, 128, 192, 32, 96, 64)

        self.maxpool = nn.MaxPool2d(3, stride=2, padding=1)

        self.a4 = Inception(480, 192,  96, 208, 16,  48,  64)
        self.b4 = Inception(512, 160, 112, 224, 24,  64,  64)
        self.c4 = Inception(512, 128, 128, 256, 24,  64,  64)
        self.d4 = Inception(512, 112, 144, 288, 32,  64,  64)
        self.e4 = Inception(528, 256, 160, 320, 32, 128, 128)

        self.a5 = Inception(832, 256, 160, 320, 32, 128, 128)
        self.b5 = Inception(832, 384, 192, 384, 48, 128, 128)

        self.avgpool = nn.AvgPool2d(8, stride=1)
        self.linear = nn.Linear(1024, 2)
        self.avg_pool = nn.AdaptiveAvgPool2d(1)

    def forward(self, x):
        out = self.pre_layers(x)
        out = self.a3(out)
        out = self.b3(out)
        out = self.maxpool(out)
        out = self.a4(out)
        out = self.b4(out)
        out = self.c4(out)
        out = self.d4(out)
        out = self.e4(out)
        out = self.maxpool(out)
        out = self.a5(out)
        out = self.b5(out)
        out = self.avg_pool(out)
        out = out.view(out.size(0), -1)
        out = self.linear(out)
        return out
    
class ZigZagLROnPlateauRestarts(torch.optim.lr_scheduler._LRScheduler):
    def __init__(self, optimizer, mode='min', lr=0.01, up_factor=1.1, down_factor=0.8, up_patience=10, down_patience=10, restart_after=30, verbose=True):
        super(ZigZagLROnPlateauRestarts).__init__()
        self.optimizer = optimizer
        self.mode = mode
        self.up_factor = 1 + up_factor
        self.down_factor = 1 - down_factor
        self.up_patience = up_patience
        self.down_patience = down_patience
        self.num_bad_epochs = 0
        self.num_good_epochs = 0
        self.prev_metric = np.Inf if self.mode == 'min' else -np.Inf
        self.best_lr = lr
        self.restart_after = restart_after
        self.verbose = verbose
        self.num_epochs = 0
        
    def step(self, metric):
        self.num_epochs += 1
        if self.mode == 'min':
            if metric < self.prev_metric:
                self.best_lr = self.optimizer.param_groups[0]['lr']
                self.num_bad_epochs = 0
                self.num_good_epochs += 1
                if self.num_good_epochs > self.up_patience:
                    old_lr = self.optimizer.param_groups[0]['lr']
                    new_lr = old_lr * self.up_factor
                    self.optimizer.param_groups[0]['lr'] = new_lr
                    if self.verbose:
                        print(f"increasing learning rate of group 0 to {new_lr:.4e}.")
                    self.num_good_epochs = 0
            else:
                self.num_bad_epochs += 1
                self.num_good_epochs = 0
                if self.num_bad_epochs > self.down_patience:
                    old_lr = self.optimizer.param_groups[0]['lr']
                    new_lr = old_lr * self.down_factor
                    self.optimizer.param_groups[0]['lr'] = new_lr
                    if self.verbose:
                        print(f"reducing learning rate of group 0 to {new_lr:.4e}.")
                    self.num_bad_epochs = 0
        else:
            if metric > self.prev_metric:
                self.best_lr = self.optimizer.param_groups[0]['lr']
                self.num_bad_epochs = 0
                self.num_good_epochs += 1
                if self.num_good_epochs > self.up_patience:
                    old_lr = self.optimizer.param_groups[0]['lr']
                    new_lr = old_lr * self.up_factor
                    self.optimizer.param_groups[0]['lr'] = new_lr
                    if self.verbose:
                        print(f"increasing learning rate of group 0 to {new_lr:.4e}.")
                    self.num_good_epochs = 0
            else:
                self.num_bad_epochs += 1
                self.num_good_epochs = 0
                if self.num_bad_epochs > self.down_patience:
                    old_lr = self.optimizer.param_groups[0]['lr']
                    new_lr = old_lr * self.down_factor
                    self.optimizer.param_groups[0]['lr'] = new_lr
                    if self.verbose:
                        print(f"reducing learning rate of group 0 to {new_lr:.4e}.")
                    self.num_bad_epochs = 0
        self.prev_metric = metric
                    
        if self.num_epochs % self.restart_after == 0:
            self.optimizer.param_groups[0]['lr'] = self.best_lr
            if self.verbose:
                print(f"restart: setting learning rate of group 0 to best learning rate value: {self.best_lr:.4e}.")
