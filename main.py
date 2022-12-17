from requests import get, post
from threading import Thread, Lock
from math import ceil


# Goes through the auth process to get the access token
def get_token(c_id, c_secret):
    # create the needed headers and body to get the token
    auth_token = client_id + ":" + secret
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
            print("authentication error, contact developer for assistance!")
            quit()
    except Exception:
        print("authentication error, contact developer for assistance!")
        quit()


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

    if r.status_code != 200: # If theres an error, quit
        print("Error getting playlist data!")
        quit()

    if len(output['items']) == 0: # Checks if the user even has playlists
        print("Error, user has no playlists!")
        quit()

    for i in range(len(output['items'])): # Loops through all playlists and gathers needed info
        playlist_data[i] = {'id': output['items'][i]['id'], 'name': output['items'][i]['name'],
                            'tracks': output['items'][i]['tracks']['total'], 'track_list': output['items'][i]['tracks']['href']}

    return playlist_data


# The multi threading function that finds the songs in a given playlist
def multi_thread_tracks(i, url, access_token):
    global track_list
    # Loop in case the playlist is greater than 100 songs, it will loop infinitely until
    # all songs in the playlist are accounted for since each request can only give up to 100 songs
    while True:
        # Send the request and get the json data
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        r = get(url, headers=headers)
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
    track_list = {}
    threads = []
    for i in playlist_data: # Uses multi threading, each thread finds all the songs in one playlist
        url = playlist_data[i]['track_list']
        temp = Thread(target=multi_thread_tracks, args=(i, url, access_token,))
        temp.start()
        threads.append(temp)
    for i in playlist_data:
        threads[i].join() # Wait for all threads to finish then return track_list
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
        print("Error getting track audio data!")
        quit()
    output = r.json()
    for j in output['audio_features']:
        lock.acquire()
        song_metrics[j['id']] = {'Danceability': j['danceability'], 'Tempo': j['tempo'], 'Energy': j['energy']}
        lock.release()



# Finds all songs danceability and tempo
def get_song_metrics(songs, access_token):
    global song_metrics
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
    return song_metrics


def get_song_matches(tempo, dance_val, energy_val, song_data, song_list):
    match_list = {"strong": [], "moderate": [], "weak": []}
    for i in song_data:
        if int(tempo[0]) <= int(song_data[i]['Tempo']) <= int(tempo[1]):
            if (float(dance_val[0]) <= float(song_data[i]['Danceability']) <= float(dance_val[1])) or (
                    float(energy_val[0]) <= float(song_data[i]['Energy']) <= float(energy_val[1])):
                if (float(dance_val[0]) <= float(song_data[i]['Danceability']) <= float(dance_val[1])) and (
                        float(energy_val[0]) <= float(song_data[i]['Energy']) <= float(energy_val[1])):
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


# Authorizing the application to get the access token
client_id = "982aa5ce43a04afe8d516ff4398a9fea"
secret = "its a secret ;)"
token = get_token(client_id, secret)

# Get users playlists and preferences
profile_link = "https://open.spotify.com/user/m8gm7ymt4s5rt9p5j98xroe4k?si=e84143878d2a453b" # users profile
cadence_up = "180" # Tempo/BPM/Cadence/Steps per min for their run
cadence_low = "170"
cadence = [cadence_low, cadence_up]
dance_up = "1" # How "danceable" the user wants the songs to be
dance_low = "0.6"
dance = [dance_low, dance_up]
energy_up = "1" # How energetic the user wants the songs to be
energy_low = "0.6"
energy = [energy_low, energy_up]
profile_id = id_from_link(profile_link)
playlists = get_playlists(profile_id, token)

# Get the ID's, names and artists of all songs in the users playlists in groups of 100
track_list = {}
lock = Lock()
tracks = find_tracks(playlists, token)

# Get each songs BPM and "danceability" to determine which songs are best to run to
song_metrics = {}
metrics = get_song_metrics(tracks, token)

# Find songs that match the users preference
matches = get_song_matches(cadence, dance, energy, metrics, tracks)
print(matches)
