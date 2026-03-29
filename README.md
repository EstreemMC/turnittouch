# Turn-It-Touch
## What is it
Our project can turn any size display into a full touchscreen TV. By using the latest developments in computer vision we were able to track our custom-printed pen to create output on the screen. Then through the ESP32 board inside the pen we were able to communicate with a python script to toggle between annotating, erasing, AI mode, and returning the device to it's normal usage, allowing natural use without any product switching friction. This can reduce the price of a Smartboard in classrooms from an average of 5 thousand dollars all the way down to just 50 dollars! Critically important as leading research from Dr. Jamie Cox found that the presence of smartboards in classrooms were shown to improve student test scores because they can adapt to many types of learners. While primarily focused on the classroom market we aim to eventually expand to the average consumer letting them turn anything into a touch screen device.

## Hardware
Our product uses a 3D printed camera mount that can be adapted to any device, from a monitor to a TV. On top of that, we created a custom Pen that uses AA batteries, for easy replacing, and extremely tight. Using a 3D printed frame, our pen can be tracked by the cameras, running a computer vision detection model, in the mount, which can be translated as ink on the screen using this software.

## Software
We used 2 major improvements in software to build. The first was new computer vision technology that we used in Python to track the pen digitally and draw on the screen and switch between different modes. The second was an OpenAI key which we used to ease the burden on teachers, when a question is put on the board you can circle it to create new questions that are similar to the one on the board and that can greatly reduce the strain on teachers while still offering unique questions.

## Finances
This is a 7 billion dollar global industry that has 2 major players who have grown complacent in their positions and as a result haven't innovated in over a decade. Our project costs under 50 dollars with a 30% profit margin.

## Photos
### AI Question Creation
Takes the information circled by the pen and creates additional problems with the same concepts using them.
![IMG_5780](https://github.com/user-attachments/assets/fb145587-4005-4d33-8a56-742948461ddc)
![IMG_5781](https://github.com/user-attachments/assets/7b397985-1e2d-4d8d-a86f-93ff3317692e)

### Custom Camera Mount
Adjustable camera mount taht can fit on any device, holds up the two cameras.
![IMG_4444](https://github.com/user-attachments/assets/004285f9-3e78-4881-91e2-16798d07e721)

### Example System
Our example system on a 24 inch monitor with the two camera mounts.
![IMG_4443](https://github.com/user-attachments/assets/509a33bf-89ad-44b0-9091-1a05cc6f19b5)
