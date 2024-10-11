# OTel exporter

In order to test, what I did was to run a MQTT broker that creates devices that would then be exported via OTLP.
To get that running, you need a few things:

- An MQTT broker
- The MQTT integration in HA subscribing to that broker
- A device definition for the MQTT device
- The OTel exporter exporting that data

### The MQTT broker

I used Mosquitto and ran it locally in a Docker container.
It seems like recent versions of the MQTT broker do not allow unsecured connections anymore.
Therefore, for local testing, I disabled security.
Do not do this if you plan on running your MQTT queue for an extended period of time.

> [!WARNING]
> THIS IS FOR TESTING ONLY

Disable security by creating a `mosquitto.conf` file and adding the following content:

```yaml
allow_anonymous true
listener 1883 0.0.0.0
```

To run the broker, I ran mosquitto in docker, mounting that config file into the docker container.
Make sure to go to the directory that contains the file when running the command below (or changing the file path to an absolute one):

```bash
docker run -it -p 1883:1883 -p 9001:9001 -v ./mosquitto.conf:/mosquitto/config/mosquitto.conf eclipse-mosquitto
```

Great, first step done. We have a MQTT broker running on port 1883.

#### (Optional) Testing your broker

On Ubuntu, I installed the `mosquitto-clients` by running:

```bash
sudo apt install -y mosquitto-clients
```

You can then run a subscriber with (the topic name will be `home/temp/living_room`):

```bash
mosquitto_sub -t "home/temp/living_room"
```

Now we have an MQTT listener and can test it by sending an MQTT message to the same topic:

```bash
mosquitto_pub -t "home/temp/living_room" -m '{"temperature": 33}'
```

It's sending a JSON message to the topic.

### Setting up the MQTT integration

I installed [the MQTT integration](https://next.home-assistant.io/integrations/mqtt).
To configure it, it was enough to put in the hostname of my machine (on Ubuntu you could just run `hostname`).
Alternatively, you can find your PC's IP address and use that.
All the other defaults are fine.

### Device definition

To define the devices you want to test, you have to add the definition to [configuration.yaml](config/configuration.yaml).
For example, a temperature sensor could be defined as follows:

```yaml
mqtt:
  sensor:
    - name: "my living room temperature sensor"
      state_topic: "home/temp/living_room"
      device_class: temperature
      unit_of_measurement: '°C'
      value_template: "{{ value_json.temperature }}"
```

Note that it will pull the value from the `temperature` field of the JSON (and we are sending JSON in the `mosquitto_pub` command above).