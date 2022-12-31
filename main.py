from time import sleep
from tkinter import *
from requests import get, post, exceptions
from base64 import b64encode, decode
from threading import Thread, Lock
from math import ceil


# Goes through the auth process to get the access token
def get_token(c_id, c_secret):
    # create the needed headers and body to get the token
    auth_token = c_id + ":" + c_secret
    headers = {
        "Authorization": f"Basic {b64encode(auth_token.encode('ascii')).decode('ascii')}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    body = {
        "grant_type": "client_credentials"
    }

    # Send a post request to the URL that will return the access token
    r = post('https://accounts.spotify.com/api/token', headers=headers, data=body)

    try: # See if the result of the request is valid, then return the access token if it is
        if r.status_code == 200:
            access_token = r.json()['access_token']
            return access_token
        else: # Quit the app if there are any errors
            error_label['text'] = "Authentication error: Contact developer for help!"
            return 0
    except Exception:
        error_label['text'] = "Authentication error: Contact developer for help!"
        return 0


# Gets a users profile id given the profile link
def id_from_link(link):
    start = 0
    end = 0
    slashes = 0
    # Finds where the 4th slash and first ? in the link are because that's the 2 characters the id is between
    for i in range(len(link)):
        if link[i:i+1] == "/":
            slashes += 1
            if slashes == 4:
                start = i+1
        if link[i:i+1] == "?":
            end = i
            break
    return link[start:end]


def get_playlists(profile, access_token):
    playlist_data = {} # Json variable that will hold the needed data to return
    # Set headers and make the request to the API to get all playlists of a user
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    r = get(f'https://api.spotify.com/v1/users/{profile}/playlists', headers=headers)
    output = r.json()

    if r.status_code == 404:  # If theres an error, quit
        error_label['text'] = "Invalid URL: Spotify profile not found"
        return 0

    if r.status_code != 200: # If theres an error, quit
        error_label['text'] = "Error getting spotify playlists, check profile URL and try again later!"
        return 0

    if len(output['items']) == 0: # Checks if the user even has playlists
        error_label['text'] = "Profile doesnt have any playlists to analyze!"
        return 0

    for i in range(len(output['items'])): # Loops through all playlists and gathers needed info
        playlist_data[i] = {'id': output['items'][i]['id'], 'name': output['items'][i]['name'],
                            'tracks': output['items'][i]['tracks']['total'], 'track_list': output['items'][i]['tracks']['href']}

    return playlist_data


# The multi threading function that finds the songs in a given playlist
def multi_thread_tracks(i, url, access_token):
    global track_list
    global threads
    # Loop in case the playlist is greater than 100 songs, it will loop infinitely until
    # all songs in the playlist are accounted for since each request can only give up to 100 songs
    while True:
        # Send the request and get the json data
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        r = get(url, headers=headers)
        # Make sure that the request was OK
        if r.status_code != 200:
            error_label['text'] = "Rate limited! Trying again in 30 seconds, do not close the app!"
            sleep(30)
            r = get(url, headers=headers)
            if r.status_code != 200:
                error_label['text'] = "Bad request, try again later!"
                for j in range(len(threads)):
                    if j != i:
                        threads[j].raise_exception()
                track_list = 0
                return
        output = r.json()
        # Iterate through all the songs and find the id, name and artist to put in the track_list dictionary
        for j in range(len(output['items'])):
            try:
                # In case of a weird bug where an "item" in the playlist is not a song
                if not isinstance(output['items'][j]['track'], dict):
                    continue
                lock.acquire()
                track_list[output['items'][j]['track']['id']] = {'Name': output['items'][j]['track']['name'],
                                                                 'Artist': output['items'][j]['track']['artists'][0]['name']}
                lock.release()
            except Exception:
                continue
        # Check if theres more songs in the playlist, if there is, loop again until all songs are accounted for
        if isinstance(output['next'], str):
            url = output['next']
        else:
            break


# Finds all the tracks in the users playlists without duplicates
def find_tracks(playlist_data, access_token):
    global track_list
    global threads
    track_list = {}
    threads = []
    for i in playlist_data: # Uses multi threading, each thread finds all the songs in one playlist
        url = playlist_data[i]['track_list']
        temp = Thread(target=multi_thread_tracks, args=(i, url, access_token,))
        temp.start()
        threads.append(temp)
    for i in playlist_data:
        threads[i].join() # Wait for all threads to finish then return track_list
    # If an error was returned, return 0
    if track_list == 0:
        return 0
    return track_list


def multi_thread_metrics(i, songs_list, access_token, final_batch, remainder):
    global song_metrics
    # Set how many songs will be in the batch, default 100, but if its the last batch its the remainder
    if final_batch:
        num_songs = remainder
    else:
        num_songs = 100
    batch = "" # String value because that's what spotify api needs
    # Iterate through the specific part of the full songs list and add the songs we need to our batch
    count = num_songs * i
    for j in range(num_songs):
        if isinstance(songs_list[count], str):
            if j+1 == num_songs: # Makes sure theres no comma at the end of the list
                batch += songs_list[count]
            else:
                batch += songs_list[count] + ","
        count += 1
    # Sending the request
    url = f"https://api.spotify.com/v1/audio-features?ids={batch}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    r = get(url, headers=headers)
    # Make sure that the request was OK
    if r.status_code != 200:
        error_label['text'] = "Rate limited! Trying again in 30 seconds, do not close the app!"
        sleep(30)
        r = get(url, headers=headers)
        if r.status_code != 200:
            error_label['text'] = "Bad request, try again later!"
            for j in range(len(threads)):
                if j != i:
                    threads[j].raise_exception()
            song_metrics = 0
            return
    output = r.json()
    for j in output['audio_features']:
        if isinstance(j, dict):
            lock.acquire()
            song_metrics[j['id']] = {'Danceability': j['danceability'], 'Tempo': j['tempo'], 'Energy': j['energy']}
            lock.release()


# Finds all songs danceability and tempo
def get_song_metrics(songs, access_token):
    global song_metrics
    global threads
    song_metrics = {} # Holds the tempo and daceability of each song
    batches, remainder = ceil(len(songs) / 100), len(songs) % 100   # Finds how many batches of 100 and how big the final batch is
    # Convert the songs dictionary to a list so we can easily iterate through
    songs_list = []
    for i in songs:
        songs_list.append(i)
    final_batch = False
    # Create "batches" amount of threads to speed up the process, each thread will handle up to 100 songs data
    threads = []
    for i in range(batches):
        if i + 1 == batches:
            final_batch = True
        temp = Thread(target=multi_thread_metrics, args=(i, songs_list, access_token, final_batch, remainder,))
        temp.start()
        threads.append(temp)
    # Wait for all threads to finish then return the data
    for i in range(batches):
        threads[i].join() # Wait for all threads to finish then return track_list
    # If an error was returned, return 0
    if song_metrics == 0:
        return 0
    return song_metrics


def get_song_matches(tempo, dance_val, energy_val, song_data, song_list):
    match_list = {"strong": [], "moderate": [], "weak": []}
    for i in song_data:
        if (float(tempo[0]) <= float(song_data[i]['Tempo']) <= float(tempo[1])) or (float(tempo[0])/2 <= float(song_data[i]['Tempo']) <= float(tempo[1])/2):
            if (float(dance_val[0]) <= float(song_data[i]['Danceability']) <= float(dance_val[1])) or (float(energy_val[0]) <= float(song_data[i]['Energy']) <= float(energy_val[1])):
                if (float(dance_val[0]) <= float(song_data[i]['Danceability']) <= float(dance_val[1])) and (float(energy_val[0]) <= float(song_data[i]['Energy']) <= float(energy_val[1])):
                    match_list['strong'].append(
                        {'id': i, 'Tempo': song_data[i]['Tempo'], 'Danceability': song_data[i]['Danceability'],
                         'Energy': song_data[i]['Energy'], 'Name': song_list[i]['Name'],
                         'Artist': song_list[i]['Artist']})
                else:
                    match_list['moderate'].append(
                        {'id': i, 'Tempo': song_data[i]['Tempo'], 'Danceability': song_data[i]['Danceability'],
                         'Energy': song_data[i]['Energy'], 'Name': song_list[i]['Name'],
                         'Artist': song_list[i]['Artist']})
            else:
                match_list['weak'].append(
                    {'id': i, 'Tempo': song_data[i]['Tempo'], 'Danceability': song_data[i]['Danceability'],
                     'Energy': song_data[i]['Energy'], 'Name': song_list[i]['Name'], 'Artist': song_list[i]['Artist']})
    return match_list


# Submits the users information and finds matches
def submit(energy_low, energy_up, dance_low, dance_up, cadence_low, cadence_up, profile_link):
    error_label['text'] = "Processing request, please wait."
    root.update()
    # Authorizing the application to get the access token
    client_id = "982aa5ce43a04afe8d516ff4398a9fea"
    secret = "2c965c0800cc4e8891e69319c8cf306e"
    token = get_token(client_id, secret)
    if token == 0:
        return

    # Set the upper and lower bounds tempo, energy and danceability
    cadence = [cadence_low, cadence_up]
    dance = [dance_low, dance_up]
    energy = [energy_low, energy_up]

    # Find the users profile and playlists
    profile_id = id_from_link(profile_link)
    playlists = get_playlists(profile_id, token)
    if playlists == 0:
        return

    # Get the ID's, names and artists of all songs in the users playlists in groups of 100
    tracks = find_tracks(playlists, token)
    if tracks == 0:
        return

    # Get each songs BPM and "danceability" to determine which songs are best to run to
    metrics = get_song_metrics(tracks, token)
    if metrics == 0:
        return

    # Find songs that match the users preference
    matches = get_song_matches(cadence, dance, energy, metrics, tracks)
    print(matches)

    return matches


# Checks the validity of the link given
def check_link(link):
    # See if a valid URL was given
    try:
        get(link)
    except Exception as e:
        if e == exceptions.MissingSchema:
            return [False, "Invalid URL: Make sure there is 'https://' in front of the url!"]
        elif e == exceptions.ConnectionError:
            return [False, "Invalid URL: URL could not be reached, make sure it is correct and try again"]
        else:
            return [False, "Invalid URL: Something went wrong, check the profile URL and try again!"]
    # See if the link is a spotify link
    if link[0:20] != "https://open.spotify":
        return [False, 'Invalid URL: Make sure the link is from open.spotify.com!']
    else:
        return [True, '']


# Verifies if all inputs are valid
def verify():
    # Check if the url is valid
    link = url_entry.get()
    link_check = check_link(link)
    if not link_check[0]:
        error_label["text"] = link_check[1]
        return
    # Check if cadence inputs are valid
    cadence_low = tempo_min.get()
    cadence_up = tempo_max.get()
    cadence_range = [cadence_low, cadence_up]
    for i in range(2):
        if not cadence_range[i].isnumeric():
            error_label["text"] = "Make sure cadence range values are numbers between 120 and 220"
            return
        if int(cadence_range[i]) > 220 or int(cadence_range[i]) < 120:
            error_label["text"] = "Make sure cadence range values are numbers between 120 and 220"
            return
    if int(cadence_low) > int(cadence_up):
        error_label["text"] = "Make sure cadence min value is less than cadence max value"
        return
    # Check if dance inputs are valid
    dance_low = dance_min.get()
    dance_up = dance_max.get()
    dance_val_range = [dance_low, dance_up]
    for i in range(2):
        if not dance_val_range[i].isnumeric():
            error_label["text"] = "Make sure dance range values are numbers between 0 and 10"
            return
        if int(dance_val_range[i]) > 10 or int(dance_val_range[i]) < 0:
            error_label["text"] = "Make sure dance range values are numbers between 0 and 10"
            return
    if int(dance_low) > int(dance_up):
        error_label["text"] = "Make sure dance min value is less than dance max value"
        return
    # Check if energy inputs are valid
    energy_low = energy_min.get()
    energy_up = energy_max.get()
    energy_val_range = [energy_low, energy_up]
    for i in range(2):
        if not energy_val_range[i].isnumeric():
            error_label["text"] = "Make sure energy range values are numbers between 0 and 10"
            return
        if int(energy_val_range[i]) > 10 or int(energy_val_range[i]) < 0:
            error_label["text"] = "Make sure energy range values are numbers between 0 and 10"
            return
    if int(energy_low) > int(energy_up):
        error_label["text"] = "Make sure energy min value is less than energy max value"
        return
    energy_low = str(int(energy_low)/10)
    energy_up = str(int(energy_up) / 10)
    dance_low = str(int(dance_low) / 10)
    dance_up = str(int(dance_up) / 10)
    submit(energy_low, energy_up, dance_low, dance_up, cadence_low, cadence_up, link)


# initialize global variables
track_list = {}
song_metrics = {}
threads = []
lock = Lock()
spotify_black = "#121212"
spotify_white = "#B3B3B3"
spotify_green = "#73D565"

# Configuring the window
root = Tk()
root.geometry("850x500")
root.title("Runify")
icon = PhotoImage(file="icon.ico")
root.iconphoto(True, icon)
root.config(background=spotify_black)
root.resizable(False, False)

# Initializing the sections of the main page
top_frame = Frame(root, width=850, height=166, bg=spotify_black)
mid_frame = Frame(root, width=850, height=166, bg=spotify_black)
bottom_frame = Frame(root, width=850, height=168, bg=spotify_black)
top_frame.grid_propagate(False)
mid_frame.grid_propagate(False)
bottom_frame.grid_propagate(False)
top_frame.grid(row=0, column=0)
mid_frame.grid(row=1, column=0)
bottom_frame.grid(row=2, column=0)

# Creating elements in the top frame
title_label = Label(top_frame, text="Runify - Spherical-S", font=("Calibri", 25), fg=spotify_white, bg=spotify_black)
url_label = Label(top_frame, text="Spotify profile URL:", font=("Calibri", 20), fg=spotify_white, bg=spotify_black)
url_entry = Entry(top_frame, font=("Calibri", 20), fg="black", bg="white", width=50)
title_label.pack(pady=7)
url_label.pack(pady=7)
url_entry.pack(pady=7)

# Creating frames for each input in the mid frame
tempo_frame = Frame(mid_frame, width=275, height=150, bg=spotify_black)
dance_frame = Frame(mid_frame, width=275, height=150, bg=spotify_black)
energy_frame = Frame(mid_frame, width=275, height=150, bg=spotify_black)
tempo_frame.grid(row=0, column=0, padx=(107, 50), pady=6)
dance_frame.grid(row=0, column=1, padx=50, pady=6)
energy_frame.grid(row=0, column=2, padx=(50, 107), pady=6)

# Elements for tempo input in the mid frame
tempo_label = Label(tempo_frame, text="Goal Cadence", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
tempo_min = Entry(tempo_frame, font=("Calibri", 20), fg="black", bg="white", width=3)
tempo_max = Entry(tempo_frame, font=("Calibri", 20), fg="black", bg="white", width=3)
tempo_min_label = Label(tempo_frame, text="Min", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
tempo_max_label = Label(tempo_frame, text="Max", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
tempo_dash = Label(tempo_frame, text="-", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
tempo_range = Label(tempo_frame, text="(120 - 220)", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
tempo_label.grid(row=0, column=0, columnspan=3, padx=2, pady=2)
tempo_min.grid(row=1, column=0, padx=2, pady=2)
tempo_dash.grid(row=1, column=1, pady=2)
tempo_max.grid(row=1, column=2, padx=2, pady=2)
tempo_min_label.grid(row=2, column=0, padx=2, pady=2)
tempo_max_label.grid(row=2, column=2, padx=2, pady=2)
tempo_range.grid(row=3, column=0, columnspan=3, padx=2, pady=2)

# Elements for dance input in the mid frame
dance_label = Label(dance_frame, text="Danceability", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
dance_min = Entry(dance_frame, font=("Calibri", 20), fg="black", bg="white", width=3)
dance_max = Entry(dance_frame, font=("Calibri", 20), fg="black", bg="white", width=3)
dance_min_label = Label(dance_frame, text="Min", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
dance_max_label = Label(dance_frame, text="Max", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
dance_dash = Label(dance_frame, text="-", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
dance_range = Label(dance_frame, text="(0 - 10)", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
dance_label.grid(row=0, column=0, columnspan=3, padx=2, pady=2)
dance_min.grid(row=1, column=0, padx=2, pady=2)
dance_dash.grid(row=1, column=1, pady=2)
dance_max.grid(row=1, column=2, padx=2, pady=2)
dance_min_label.grid(row=2, column=0, padx=2, pady=2)
dance_max_label.grid(row=2, column=2, padx=2, pady=2)
dance_range.grid(row=3, column=0, columnspan=3, padx=2, pady=2)

# Elements for energy input in the mid frame
energy_label = Label(energy_frame, text="Energy Level", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
energy_min = Entry(energy_frame, font=("Calibri", 20), fg="black", bg="white", width=3)
energy_max = Entry(energy_frame, font=("Calibri", 20), fg="black", bg="white", width=3)
energy_min_label = Label(energy_frame, text="Min", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
energy_max_label = Label(energy_frame, text="Max", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
energy_dash = Label(energy_frame, text="-", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
energy_range = Label(energy_frame, text="(0 - 10)", font=("Calibri", 18), fg=spotify_white, bg=spotify_black)
energy_label.grid(row=0, column=0, columnspan=3, padx=2, pady=2)
energy_min.grid(row=1, column=0, padx=2, pady=2)
energy_dash.grid(row=1, column=1, pady=2)
energy_max.grid(row=1, column=2, padx=2, pady=2)
energy_min_label.grid(row=2, column=0, padx=2, pady=2)
energy_max_label.grid(row=2, column=2, padx=2, pady=2)
energy_range.grid(row=3, column=0, columnspan=3, padx=2, pady=2)

# Elements in the bottom frame
error_label = Label(bottom_frame, text="", font=("Calibri", 18), fg="red", bg=spotify_black)
submit_image = PhotoImage(file="submit.png")
submit_button = Button(bottom_frame, cursor="hand2", image=submit_image, borderwidth=0, bg=spotify_black, activebackground=spotify_black, command=verify)
error_label.pack(pady=20)
submit_button.pack(pady=15)


# Starts the application
root.mainloop()