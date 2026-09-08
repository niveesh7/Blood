import os
import numpy as np
import cv2
import tensorflow as tf
from tensorflow.keras import layers, models
from pathlib import Path
from tkinter import Tk, Frame, Button, Label, filedialog, Canvas, Text
from datetime import datetime
from PIL import Image, ImageTk

# It is Path where the fingerprint dataset is stored
DATASET_PATH = r"C:\Users\Narendra\Downloads\FYP_Naik\fingerprint_Dataset"
MODEL_PATH = "blood_group_model.keras"  # Path to save/load the model

blood_groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']

def load_data(base_path):
    """Load the dataset and prepare images and labels."""
    images = []
    labels = []
    for label in blood_groups:
        label_path = Path(base_path) / label
        if not os.path.exists(label_path):
            print(f"Warning: The directory {label_path} does not exist.")
            continue
        for img_file in os.listdir(label_path):
            img_path = label_path / img_file
            img = cv2.imread(str(img_path))
            if img is None:
                print(f"Warning: Could not read file {img_path}. Skipping.")
                continue
            
            img = cv2.resize(img, (128, 128))  # Resize
            img = img.astype('float32') / 255.0  # Normalize
            images.append(img)
            labels.append(blood_groups.index(label))  # Encode
    return np.array(images), np.array(labels)

def build_model_with_transfer_learning():
    """Build and compile a CNN model using transfer learning with EfficientNetB0."""
    base_model = tf.keras.applications.EfficientNetB0(include_top=False, weights='imagenet', input_shape=(128, 128, 3))
    base_model.trainable = False  # Start by freezing the base model

    model = models.Sequential([
        base_model,
        layers.GlobalAveragePooling2D(),
        layers.BatchNormalization(),
        layers.Dense(256, activation='relu'),
        layers.Dropout(0.5),
        layers.Dense(len(blood_groups), activation='softmax')
    ])
    
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.00001),  # Initial learning rate
                  loss='sparse_categorical_crossentropy', 
                  metrics=['accuracy'])
    return model

def train_model(images, labels):
    """Train the CNN model on the given dataset with data augmentation and early stopping."""
    model = build_model_with_transfer_learning()

    # Data augmentation with enhanced settings
    datagen = tf.keras.preprocessing.image.ImageDataGenerator(
        rotation_range=30,
        width_shift_range=0.2,
        height_shift_range=0.2,
        shear_range=0.2,
        zoom_range=0.2,
        horizontal_flip=True,
        fill_mode='nearest',
        brightness_range=[0.8, 1.2],
        channel_shift_range=0.2,
        validation_split=0.2  # Use a portion for validation
    )
    
    datagen.fit(images)

    # Compute class weights
    class_weights = {i: 1.0 for i in range(len(blood_groups))}
    unique, counts = np.unique(labels, return_counts=True)
    total_samples = len(labels)
    
    for i, count in zip(unique, counts):
        class_weights[i] = total_samples / (len(unique) * count)

    early_stopping = tf.keras.callbacks.EarlyStopping(
        monitor='val_accuracy', 
        patience=10,
        restore_best_weights=True, 
        verbose=1
    )

    lr_schedule = tf.keras.callbacks.ReduceLROnPlateau(
        monitor='val_loss', 
        factor=0.2, 
        patience=5, 
        min_lr=1e-6,
        verbose=1
    )

    # Initial training
    history = model.fit(datagen.flow(images, labels, batch_size=32),
                        epochs=50,
                        validation_split=0.2,
                        callbacks=[early_stopping, lr_schedule],
                        class_weight=class_weights)

    # Unfreeze more layers for fine-tuning
    for layer in model.layers[0].layers[-30:]:  # Unfreeze last 30 layers
        layer.trainable = True
    
    # Re-compile the model
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.000001), 
                  loss='sparse_categorical_crossentropy', 
                  metrics=['accuracy'])
    
    # Continue training
    model.fit(datagen.flow(images, labels, batch_size=32),
              epochs=50,
              validation_split=0.2,
              callbacks=[early_stopping, lr_schedule],
              class_weight=class_weights)
    
    model.save(MODEL_PATH)

def load_model():
    """Load the trained model from file."""
    return tf.keras.models.load_model(MODEL_PATH)

def predict_blood_group(model, img_path):
    """Predict blood group based on the input image."""
    img = cv2.imread(img_path)
    img = cv2.resize(img, (128, 128))  # Resize
    img = img.astype('float32') / 255.0  # Normalize
    img = np.expand_dims(img, axis=0)  # Add batch dimension
    predictions = model.predict(img)
    return np.argmax(predictions)

# GUI application code
class BloodGroupApp(Frame):
    """Main application class."""
    def __init__(self, master=None):
        super().__init__(master)
        self.master = master
        self.model = None
        self.file_path = None
        self.history_data = []
        self.initUI()

    def initUI(self):
        self.master.title("Blood Group Detection System")
        self.master.geometry("800x600")
        self.master.config(bg='lightblue')

        header_frame = Frame(self.master, bg='darkblue', padx=10, pady=10)
        header_frame.pack(fill='x')

        self.menu_button = Button(header_frame, text="☰", command=self.toggle_menu, font=("Helvetica", 16), bg='darkblue', fg="white", bd=0)
        self.menu_button.pack(side='left')

        title_label = Label(header_frame, text="Blood Group Detection System", font=("Helvetica", 16), bg='darkblue', fg="white")
        title_label.pack(side='left', padx=10)

        about_button = Button(header_frame, text="About Us", command=self.show_about, font=("Helvetica", 12), bg='blue', fg="white", bd=0)
        about_button.pack(side='right')

        content_frame = Frame(self.master, bg='lightblue', padx=40, pady=20)
        content_frame.pack(expand=True)

        self.image_label = Label(content_frame, text="Upload a fingerprint image:", font=("Helvetica", 16), bg='lightblue')
        self.image_label.pack(pady=10)

        self.img_canvas = Canvas(content_frame, width=200, height=200, bg='white')
        self.img_canvas.pack(pady=10)

        self.btn_select = Button(content_frame, text="Select Image", command=self.select_image, font=("Helvetica", 14), bg="white", fg="black", bd=0)
        self.btn_select.pack(pady=10)

        self.btn_predict = Button(content_frame, text="Predict Blood Group", command=self.predict, font=("Helvetica", 14), state="disabled", bg="white", fg="black", bd=0)
        self.btn_predict.pack(pady=10)

        self.result_label = Label(content_frame, text="", font=("Helvetica", 20), bg='lightblue', fg="black")
        self.result_label.pack(pady=20)

        self.history_label = Label(content_frame, text="History", font=("Helvetica", 18), bg='lightblue')
        self.history_label.pack(pady=10)

        self.history_text = Text(content_frame, height=8, width=50, state='disabled')
        self.history_text.pack(pady=10)

        self.menu_frame = Frame(self.master, bg='lightgray', width=150, height=600)
        self.menu_options = [
            ("Blood Info", self.show_blood_info),
            ("Service Feedback", self.show_feedback),
            ("Others", self.show_others),
        ]
        for text, command in self.menu_options:
            btn = Button(self.menu_frame, text=text, command=command, bg='lightgray', fg='black', font=("Helvetica", 12), bd=0)
            btn.pack(fill='x')

        self.menu_frame.pack(side='left', anchor='nw', fill='y')
        self.menu_frame.pack_forget()  # Hide menu by default

    def toggle_menu(self):
        """Show or hide the menu."""
        if self.menu_frame.winfo_ismapped():
            self.menu_frame.pack_forget()
        else:
            self.menu_frame.pack(side='left', anchor='nw', fill='y')

    def show_blood_info(self):
        """Display blood information."""
        self.result_label.config(text="Blood Info: Check various blood types and their characteristics.")

    def show_feedback(self):
        """Display service feedback options."""
        self.result_label.config(text="Service Feedback: We value your feedback to improve our services.")

    def show_others(self):
        """Other options."""
        self.result_label.config(text="Other Services: Various other related services will be available.")

    def show_about(self):
        """Show about information."""
        self.result_label.config(text="About Us: This system predicts blood groups from fingerprints.")

    def select_image(self):
        """Select the fingerprint image file."""
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg;*.jpeg;*.png")])
        if file_path:  # Check if a file was selected
            self.file_path = file_path
            self.btn_predict.config(state="normal")
            self.display_image(file_path)

    def display_image(self, file_path):
        """Display the selected image on canvas."""
        img = Image.open(file_path)
        img = img.resize((200, 200), Image.LANCZOS)  # Use LANCZOS for higher quality
        img_tk = ImageTk.PhotoImage(img)  # Convert the image for Tkinter
        self.img_canvas.create_image(0, 0, anchor='nw', image=img_tk)
        self.img_canvas.image = img_tk  # Keep a reference to avoid garbage collection

    def predict(self):
        """Predict blood group based on the selected image."""
        if self.model is None:
            self.model = load_model()  # Load the model if not already loaded
        blood_group_index = predict_blood_group(self.model, self.file_path)
        blood_group = blood_groups[blood_group_index]
        self.result_label.config(text=f"Predicted Blood Group: {blood_group}")

        # Add to history
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.history_data.append(f"{blood_group} at {timestamp}")
        self.update_history()
 
    def update_history(self):
        """Update the history text area."""
        self.history_text.config(state='normal')
        self.history_text.delete(1.0, 'end')  # Clear previous history
        for entry in self.history_data:
            self.history_text.insert('end', entry + "\n")
        self.history_text.config(state='disabled')

if __name__ == "__main__":
    root = Tk()
    app = BloodGroupApp(master=root)
    
    # Load the dataset and initial model training
    images, labels = load_data(DATASET_PATH)
    
    if len(images) > 0 and len(labels) > 0:
        # Uncomment this line for initial training; remove it or comment it out afterward
        # train_model(images, labels)
        app.model = load_model()  # Load the model if it has already been trained
    else:
        print("No images were loaded. Make sure your dataset is correctly organized.")
    
    app.pack()
    root.mainloop()
