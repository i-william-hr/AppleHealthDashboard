# AppleHealthDashboard
This takes data from an Apple watch, saves it into a database and then serves a webserver local on port 8080

#Get data from iPhone

Go into  the Health app - Select your Profile - Select Export all data and save the ZIP file

WARNING: This can be multiple GB even as ZIP




#Install python and dependencies

Python depends on your OS - This was tested on MacOS and Windows

Windows: py -m pip install Flask

MacOS/Linux: pip3 install Flask waitress

#Save the script in a local directory, if desired you can also download the Powershell script to start it in backgroud





#Import data

Put your export.xml from the ZIP in the app directory

Windows: py .\health_dashboard_final.py import

MacOS/Linux: python .\health_dashboard_final.py import

This will output the imported record amount at the end.





#Start the script

Windows 1: Use the Windows PowerShell script to start it (Right click - Run in PowerShell)

Windows 2: Open Powershell (or cmd) and enter you app directory, then run py .\health_dashboard_final.py serve

MacOS/Linux: python .\health_dashboard_final.py serve




Open http://127.0.0.1:8080/ onj your browser and enjoy your data
