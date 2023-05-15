import os
import ast
import nltk
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import torch
import torchvision.transforms as transforms
from torch.utils.data import Dataset
from PIL import Image
import glob
from multiprocessing import Pool
from tqdm import tqdm

import matplotlib
matplotlib.use('Agg')

class Data():
    """
    A container for the data used to train and evaluate the POS tagging model.

    Args:
        csv_name: The path to the CSV file containing the data.

    Attributes:
        df: The Pandas DataFrame object containing the data.
        human_paragraphs: A list of lists of strings, where each inner list represents a paragraph of human answers.
        chatgpt_paragraphs: A list of lists of strings, where each inner list represents a paragraph of ChatGPT answers.

    Methods:
        __init__(self, csv_name):
            Initializes the class and reads the data from the CSV file.
        _read_csv(self):
            Reads the CSV file and stores the data in the following variables:
                * `self.df`: The Pandas DataFrame object.
                * `self.human_paragraphs`: A list of lists of strings, where each inner list represents a paragraph of human answers.
                * `self.chatgpt_paragraphs`: A list of lists of strings, where each inner list represents a paragraph of ChatGPT answers.
        _cpu_thread_worker(self, paragraph, itr, name):
            A CPU thread worker that saves the given paragraph to a file.
        save_pos_tagged_images(self, name, images_dir):
            Saves the given dataset to a directory in torch format.
        save_torch_data_batches(self, folder_path):
            Saves the given dataset to a directory in torch format.
        get_train_test_val_data(self, batch_path=None, split=[0.8, 0.1, 0.1]):
            Gets the training, testing, and validation datasets from the given batch path.
    """

    def __init__(self, csv_name):
        """
        Initializes the class and reads the data from the CSV file.
        """

        self.csv_name = csv_name
        self._read_csv()

    def _read_csv(self):
        """
        Read the CSV file and store the data in the following variables:

        * `self.df`: The Pandas DataFrame object.
        * `self.human_paragraphs`: A list of lists of strings, where each inner list represents a paragraph of human answers.
        * `self.chatgpt_paragraphs`: A list of lists of strings, where each inner list represents a paragraph of ChatGPT answers.
        """

        self.df = pd.read_csv(self.csv_name)

        # Create a list of lists of strings, where each inner list represents a paragraph of human/chatgpt answers.
        self.human_paragraphs = [''.join(ast.literal_eval(human_paragraph)).replace('\n', '').split('.') 
                                for human_paragraph in list(self.df['human_answers'])]
        self.chatgpt_paragraphs = [''.join(ast.literal_eval(chatgpt_paragraph)).replace('\n', '').split('.') 
                                for chatgpt_paragraph in list(self.df['chatgpt_answers'])]
        
    def _cpu_thread_worker(self, paragraph, itr, name):
        """
        A CPU thread worker that saves the given paragraph to a file.

        Args:
            paragraph: The paragraph to save.
            itr: The iteration number.
            name: The name of the dataset.
        """

        if len(paragraph) < 3:
            return

        arrs = []
        arr_lens = []
        for i in range(len(paragraph)):
            sentence = paragraph[i] + '.'
            arr, arr_len = self.pos_obj.get_tags(sentence)
            arrs.append(arr)
            arr_lens.append(arr_len)

        # The function iterates over the paragraph, in groups of three sentences.
        # For each group of three sentences, the function does the following:
        #   * Finds the minimum and maximum lengths of the sentences in the group.
        #   * Creates a new array, where each element is the corresponding element from the sentences in the group, padded with zeros to the maximum length.
        #   * Creates a contour plot of the new array.
        #   * Saves the contour plot to a file.

        for i in range(0, len(paragraph) - 2):
            try:
                min_len = min(arr_lens[i:i+3])
                max_len = max(arr_lens[i:i+3])
                arrs_ = []
                for j in range(3):
                    arr = arrs[i+j].copy()
                    arr.extend([0]*(max_len - arr_lens[i+j]))
                    arrs_.append(arr)

                # Stack the arrays vertically
                data = np.vstack(arrs_)
                
                # Create a contour plot
                plt.contourf(data, cmap='hsv')

                # Set Plot Axis as OFF
                plt.axis('off')
                plt.savefig(f"{self.images_dir}{name}/{name}_{itr}_{mini_itr}.png",bbox_inches='tight', pad_inches=0, dpi=100)
                plt.close()
                
                mini_itr += 1

            except Exception as e:
                print(e)     

    def save_pos_tagged_images(self, name, images_dir):
        """
        Saves the given dataset to a directory in torch format.

        Args:
            name: The name of the dataset.
            images_dir: The path to the directory where the data will be saved.
        """

        # Set the data store path.
        self.images_dir = images_dir

        # If the name is "human", use the human paragraphs. Otherwise, use the chatgpt paragraphs.
        if name.lower() == "human":
            paragraphs = self.human_paragraphs
            name = name.lower()
        else:
            paragraphs = self.chatgpt_paragraphs
            name = "ai"

        try:
            os.mkdir(f"{self.images_dir}/{name}")
        except FileExistsError:
            pass

        # Create an instance of the POSTags class.
        self.pos_obj = POSTags()

        # Create a multiprocessing pool.
        with multiprocessing.Pool() as pool:
            # Create a list to store the results of the CPU thread worker.
            results = []

            # Iterate over the paragraphs and save them to files.
            for paragraph in tqdm(paragraphs):
                # Apply the CPU thread worker to the paragraph.
                result = pool.apply_async(self._cpu_thread_worker, args=(paragraph, itr, name))
                results.append(result)
                itr += 1

            # Iterate over the results and get the images.
            for result in tqdm(results):
                result.get()

    def save_torch_data_batches(self, folder_path):
        """
        Saves the given dataset to a directory in torch format.

        Args:
            folder_path: The path to the directory where the data will be saved.
        """

        # Set the data store path.
        self.data_store_path = folder_path

        # Define the transform to apply on the images.
        transform = transforms.Compose([transforms.Resize((50, 50)), transforms.ToTensor()])

        # Create an instance of the custom dataset.
        dataset = POSImageDataset(self.data_store_path, transform=transform)

        # Create a DataLoader to handle batch loading.
        dataloader = torch.utils.data.DataLoader(dataset, batch_size=10000, shuffle=True)

        # Create a list to store batch class labels.
        batch_labels = []

        # Iterate over the DataLoader and save the batches to files.
        for batch_idx, (batch, labels) in tqdm(enumerate(dataloader), total=len(dataloader)):
            # Save the batch to a file.
            torch.save(batch, f"{self.data_store_path}/batches/data_batch_{batch_idx+1}.pt")

            # Add the batch labels to the list.
            batch_labels.extend(labels.tolist())

        # Write the batch labels to a META file.
        with open(f"{self.data_store_path}/batches/batches.META", "w") as f:
            for label in batch_labels:
                f.write(f"{label}\n")


    def get_train_test_val_data(self, batch_path=None, split=[0.8, 0.1, 0.1]):
        """
        Gets the training, testing, and validation datasets from the given batch path.

        Args:
            batch_path: The path to the batch directory.
            split: The split of the data, in the form [train_size, test_size, val_size].

        Returns:
            A tuple of the training, testing, and validation datasets.
        """

        # If the batch path is not given, use the default batch directory.
        if batch_path is None:
            batch_path = f"{self.data_store_path}/batches/"

        # Get the list of .pt files in the batch directory.
        file_paths = glob.glob(batch_path + '.pt')

        # Load the META file to get the labels.
        batch_labels = []
        with open(f"{batch_path}batches.META", "r") as f:
            for line in f:
                label = int(line.strip())
                batch_labels.append(label)

        # Load the tensors from the .pt files and concatenate them.
        all_tensors = []
        for file_path in file_paths:
            tensor = torch.load(file_path, map_location=torch.device('cpu'))
            all_tensors.append(tensor)
        all_tensors = torch.cat(all_tensors)

        # Create an instance of the custom dataset with data normalization applied.
        mean = [0.0028, 0.0024, 0.0006]
        std = [0.0014, 0.0010, 0.0011]
        transform = transforms.Compose([transforms.ToPILImage(),
                                            transforms.ToTensor(),
                                            transforms.Normalize(mean, std)])

        # Create the training, testing, and validation datasets.
        dataset = POSImageTensorDataset(all_tensors, batch_labels, transform)
        train_set, test_set = torch.utils.data.random_split(dataset, [(split[0]+split[2])*len(dataset), split[1]*len(dataset)])
        train_set, val_set  = torch.utils.data.random_split(train_set, [split[0]*len(dataset), split[2]*len(dataset)])

        return (train_set, test_set, val_set)

class POSImageTensorDataset(Dataset):
    """
    This class provides a dataset of images and labels for parts-of-speech (POS) tagging.

    Attributes:
        images: A tensor of images.
        labels: A tensor of labels.
        transform: A transform that is applied to each image.

    Methods:
        __init__(self, images, labels, transform=None):
            Initializes the class.

        __len__(self):
            Returns the number of images in the dataset.

        __getitem__(self, index):
            Returns the image and its corresponding label at the given index.
    """

    def __init__(self, images, labels, transform=None):
        """
        Initializes the class.

        Args:
            images: A tensor of images.
            labels: A tensor of labels.
            transform: A transform that is applied to each image.
        """

        # The tensor of images.
        self.images = images

        # The tensor of labels.
        self.labels = labels

        # A transform that is applied to each image.
        self.transform = transform

    def __len__(self):
        """
        Returns the number of images in the dataset.
        """

        return len(self.images)

    def __getitem__(self, index):
        """
        Returns the image and its corresponding label at the given index.
        """

        # The image and label at the given index.
        image = self.images[index]
        label = self.labels[index]

        # Move the image tensor to CPU and convert to NumPy ndarray.
        image = image.cpu().numpy()

        # Convert NumPy ndarray to PIL Image.
        image = Image.fromarray(np.uint8(image), mode='RGB')

        # Apply data transformation if available.
        if self.transform is not None:
            # Convert PIL Image to NumPy ndarray.
            image = np.array(image)
            # Convert ndarray to Tensor.
            image = torch.from_numpy(image)
            image = self.transform(image)

        # Return the image and its label.
        return image, label
    
class POSImageDataset(Dataset):
    """
    This class provides a dataset of images for parts-of-speech (POS) tagging.

    Attributes:
        root_dir: The directory where the images are stored.
        transform: A transform that is applied to each image.

    Methods:
        __init__(self, root_dir, transform=None):
            Initializes the class.

        __len__(self):
            Returns the number of images in the dataset.

        __getitem__(self, index):
            Returns the image and its corresponding label at the given index.
    """

    def __init__(self, root_dir, transform=None):
        """
        Initializes the class.

        Args:
            root_dir: The directory where the images are stored.
            transform: A transform that is applied to each image.
        """

        self.root_dir = root_dir

        # A transform that is applied to each image.
        self.transform = transform

        # The list of image files.
        self.image_files = glob.glob(root_dir + '**/*.png', recursive=True)

        # The list of classes.
        self.classes = sorted(set([image_file.split(os.sep)[-2] for image_file in self.image_files]))

        # A dictionary that maps classes to their corresponding indices.
        self.class_to_idx = {cls: i for i, cls in enumerate(self.classes)}

    def __len__(self):
        """
        Returns the number of images in the dataset.
        """

        return len(self.image_files)

    def __getitem__(self, index):
        """
        Returns the image and its corresponding label at the given index.
        """

        # The index of the image file.
        image_file = self.image_files[index]

        image_path = image_file 
        image = Image.open(image_path).convert("RGB")
        label = self.class_to_idx[image_file.split(os.sep)[-2]]

        # If a transform is defined, apply it to the image.
        if self.transform is not None:
            image = self.transform(image)

        # Return the image and its label.
        return image, label
            
class POSTags:
    """
    This class provides methods for getting parts-of-speech (POS) tags from a sentence.

    Attributes:
        pos_dict: A dictionary that maps POS tags to their corresponding integer values.

    Methods:
        __init__(self):
            Initializes the class.

        get_tags(self, sentence):
            Gets the POS tags for a sentence.
    """

    def __init__(self):
        """
        Initializes the class.

        The `pos_dict` attribute is initialized with a dictionary that maps POS tags to their corresponding integer values.
        """

        self.pos_dict = {'CC': 1, 'CD': 2, 'DT': 3, 'EX': 4, 'FW': 5, 'IN': 6, 'JJ': 7, 'JJR': 8,
                         'JJS': 9, 'LS': 10, 'MD': 11, 'NN': 12, 'NNS': 13, 'NNP': 14, 'NNPS': 15,
                         'PDT': 16, 'POS': 17, 'PRP': 18, 'PRP$': 19, 'RB': 20, 'RBR': 21, 'RBS': 22,
                         'RP': 23, 'SYM': 24, 'TO': 25, 'UH': 26, 'VB': 27, 'VBD': 28, 'VBG': 29,
                         'VBN': 30, 'VBP': 31, 'VBZ': 32, 'WDT': 33, 'WP': 34, 'WP$': 35, 'WRB': 36}

    def get_tags(self, sentence):
        """
        Gets the POS tags for a sentence.

        The sentence is first tokenized into words and POS tags. The POS tags are then looked up in the `pos_dict` attribute and converted to their corresponding integer values. The resulting list of integer values is returned.

        Args:
            sentence: The sentence to get the POS tags for.

        Returns:
            A list of integer values representing the POS tags for the sentence.
        """

        # Tokenize the sentence into words and POS tags.
        words_and_tags = nltk.pos_tag(nltk.word_tokenize(sentence))

        # Get the POS tags for each word.
        pos_tags = [self.pos_dict.get(tag, 0) for word, tag in words_and_tags]

        # Remove any POS tags that are not defined.
        pos_tags = [pos_tag_ for pos_tag_ in pos_tags if pos_tag_ != 0]

        return pos_tags