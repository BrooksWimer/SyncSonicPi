package main

import (
	"encoding/binary"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/godbus/dbus/v5"
)

const (
	DEVICE_NAME        = "Sync-Sonic"
	SERVICE_UUID       = "19b10000-e8f2-537e-4f6c-d104768a1214"
	CHARACTERISTIC_UUID = "19b10001-e8f2-537e-4f6c-d104768a1217"
)

// Message types for communication
const (
	MESSAGE_TYPE_PING  = 0x01
	MESSAGE_TYPE_PONG  = 0x02
	MESSAGE_TYPE_ERROR = 0x03
)

// Timer intervals
const (
	HEARTBEAT_INTERVAL        = 5 * time.Second
	CONNECTION_CHECK_INTERVAL = 1 * time.Second
)

// Characteristic represents a GATT characteristic
type Characteristic struct {
	Path        dbus.ObjectPath
	Bus         *dbus.Conn
	UUID        string
	Service     *Service
	Flags       []string
	Value       []byte
	Notifying   bool
	PingCount   uint32
}

// Service represents a GATT service
type Service struct {
	Path           dbus.ObjectPath
	Bus           *dbus.Conn
	UUID          string
	Primary       bool
	Characteristic *Characteristic
}

// Advertisement represents a BLE advertisement
type Advertisement struct {
	Path            dbus.ObjectPath
	Bus            *dbus.Conn
	Type           string
	LocalName      string
	IncludeTxPower bool
}

// Application represents the main GATT application
type Application struct {
	Path           dbus.ObjectPath
	Bus           *dbus.Conn
	Service       *Service
	Advertisement *Advertisement
	Connected     bool
	StopChan      chan struct{}
}

// DBusObject interface defines the methods required for D-Bus objects
type DBusObject interface {
	GetAll(iface string) (map[string]dbus.Variant, error)
	Get(iface, prop string) (dbus.Variant, error)
	Set(iface, prop string, value dbus.Variant) error
	GetDBusPath() dbus.ObjectPath
	GetDBusInterface() string
}

// NewCharacteristic creates a new characteristic
func NewCharacteristic(bus *dbus.Conn, service *Service) *Characteristic {
	return &Characteristic{
		Path:    dbus.ObjectPath("/org/bluez/example/service0/char0"),
		Bus:     bus,
		UUID:    CHARACTERISTIC_UUID,
		Service: service,
		Flags:   []string{"read", "write", "notify"},
	}
}

// NewService creates a new service
func NewService(bus *dbus.Conn) *Service {
	return &Service{
		Path:     dbus.ObjectPath("/org/bluez/example/service0"),
		Bus:      bus,
		UUID:     SERVICE_UUID,
		Primary:  true,
	}
}

// NewAdvertisement creates a new advertisement
func NewAdvertisement(bus *dbus.Conn) *Advertisement {
	return &Advertisement{
		Path:            dbus.ObjectPath("/org/bluez/example/advertisement0"),
		Bus:            bus,
		Type:           "peripheral",
		LocalName:      DEVICE_NAME,
		IncludeTxPower: true,
	}
}

// NewApplication creates a new application
func NewApplication(bus *dbus.Conn) *Application {
	service := NewService(bus)
	service.Characteristic = NewCharacteristic(bus, service)
	
	return &Application{
		Path:           dbus.ObjectPath("/org/bluez/example"),
		Bus:           bus,
		Service:       service,
		Advertisement: NewAdvertisement(bus),
		StopChan:      make(chan struct{}),
	}
}

// GetProperties returns the characteristic properties
func (c *Characteristic) GetProperties() map[string]dbus.Variant {
	props := make(map[string]dbus.Variant)
	props["Service"] = dbus.MakeVariant(c.Service.Path)
	props["UUID"] = dbus.MakeVariant(c.UUID)
	props["Flags"] = dbus.MakeVariant(c.Flags)
	return props
}

// GetProperties returns the service properties
func (s *Service) GetProperties() map[string]dbus.Variant {
	props := make(map[string]dbus.Variant)
	props["UUID"] = dbus.MakeVariant(s.UUID)
	props["Primary"] = dbus.MakeVariant(s.Primary)
	props["Characteristics"] = dbus.MakeVariant([]dbus.ObjectPath{s.Characteristic.Path})
	return props
}

// GetProperties returns the advertisement properties
func (a *Advertisement) GetProperties() map[string]dbus.Variant {
	props := make(map[string]dbus.Variant)
	props["Type"] = dbus.MakeVariant(a.Type)
	props["LocalName"] = dbus.MakeVariant(a.LocalName)
	props["IncludeTxPower"] = dbus.MakeVariant(a.IncludeTxPower)
	return props
}

// GetProperties returns the application properties
func (app *Application) GetProperties() map[string]dbus.Variant {
	props := make(map[string]dbus.Variant)
	props["Services"] = dbus.MakeVariant([]dbus.ObjectPath{app.Service.Path})
	return props
}

// ReadValue handles read requests
func (c *Characteristic) ReadValue(options map[string]dbus.Variant) ([]byte, error) {
	log.Println("Read request received")
	return []byte("Hello from Pi!"), nil
}

// WriteValue handles write requests
func (c *Characteristic) WriteValue(value []byte, options map[string]dbus.Variant) error {
	if len(value) < 5 {
		return fmt.Errorf("invalid message length")
	}

	messageType := value[0]
	count := binary.BigEndian.Uint32(value[1:5])

	switch messageType {
	case MESSAGE_TYPE_PING:
		log.Printf("Received PING with count: %d", count)
		c.PingCount = count

		// Create PONG response
		response := make([]byte, 5)
		response[0] = MESSAGE_TYPE_PONG
		binary.BigEndian.PutUint32(response[1:5], count)

		// Send PONG response
		if err := c.SendNotification(response); err != nil {
			return fmt.Errorf("failed to send PONG: %v", err)
		}
		log.Printf("Sent PONG with count: %d", count)

	default:
		return fmt.Errorf("unknown message type: %d", messageType)
	}

	return nil
}

// SendNotification sends a notification to the client
func (c *Characteristic) SendNotification(value []byte) error {
	if !c.Notifying {
		return fmt.Errorf("notifications not enabled")
	}

	props := make(map[string]dbus.Variant)
	props["Value"] = dbus.MakeVariant(value)

	return c.Bus.Emit(c.Path, "org.freedesktop.DBus.Properties.PropertiesChanged",
		"org.bluez.GattCharacteristic1", props, []string{})
}

// Implement D-Bus interface methods for Application
func (app *Application) GetAll(iface string) (map[string]dbus.Variant, error) {
	if iface == "org.bluez.GattApplication1" {
		return app.GetProperties(), nil
	}
	return nil, fmt.Errorf("unknown interface: %s", iface)
}

func (app *Application) Get(iface, prop string) (dbus.Variant, error) {
	props := app.GetProperties()
	if v, ok := props[prop]; ok {
		return v, nil
	}
	return dbus.Variant{}, fmt.Errorf("unknown property: %s", prop)
}

func (app *Application) Set(iface, prop string, value dbus.Variant) error {
	return fmt.Errorf("property %s is read-only", prop)
}

func (app *Application) GetDBusPath() dbus.ObjectPath {
	return app.Path
}

func (app *Application) GetDBusInterface() string {
	return "org.bluez.GattApplication1"
}

// Start starts the application
func (app *Application) Start() error {
	log.Println("Starting application...")
	log.Printf("Application path: %s", app.Path)
	log.Printf("Service path: %s", app.Service.Path)
	log.Printf("Characteristic path: %s", app.Service.Characteristic.Path)
	log.Printf("Advertisement path: %s", app.Advertisement.Path)

	// Export objects with proper interfaces
	log.Println("Exporting application...")
	if err := app.Bus.Export(app, app.Path, "org.bluez.GattApplication1"); err != nil {
		return fmt.Errorf("failed to export application: %v", err)
	}
	log.Println("Application exported successfully")

	log.Println("Exporting service...")
	if err := app.Bus.Export(app.Service, app.Service.Path, "org.bluez.GattService1"); err != nil {
		return fmt.Errorf("failed to export service: %v", err)
	}
	log.Println("Service exported successfully")

	log.Println("Exporting characteristic...")
	if err := app.Bus.Export(app.Service.Characteristic, app.Service.Characteristic.Path, "org.bluez.GattCharacteristic1"); err != nil {
		return fmt.Errorf("failed to export characteristic: %v", err)
	}
	log.Println("Characteristic exported successfully")

	log.Println("Exporting advertisement...")
	if err := app.Bus.Export(app.Advertisement, app.Advertisement.Path, "org.bluez.LEAdvertisement1"); err != nil {
		return fmt.Errorf("failed to export advertisement: %v", err)
	}
	log.Println("Advertisement exported successfully")

	// Export properties interface for each object
	log.Println("Exporting application properties...")
	if err := app.Bus.Export(app, app.Path, "org.freedesktop.DBus.Properties"); err != nil {
		return fmt.Errorf("failed to export application properties: %v", err)
	}
	log.Println("Application properties exported successfully")

	log.Println("Exporting service properties...")
	if err := app.Bus.Export(app.Service, app.Service.Path, "org.freedesktop.DBus.Properties"); err != nil {
		return fmt.Errorf("failed to export service properties: %v", err)
	}
	log.Println("Service properties exported successfully")

	log.Println("Exporting characteristic properties...")
	if err := app.Bus.Export(app.Service.Characteristic, app.Service.Characteristic.Path, "org.freedesktop.DBus.Properties"); err != nil {
		return fmt.Errorf("failed to export characteristic properties: %v", err)
	}
	log.Println("Characteristic properties exported successfully")

	log.Println("Exporting advertisement properties...")
	if err := app.Bus.Export(app.Advertisement, app.Advertisement.Path, "org.freedesktop.DBus.Properties"); err != nil {
		return fmt.Errorf("failed to export advertisement properties: %v", err)
	}
	log.Println("Advertisement properties exported successfully")

	// Register application on hci0
	log.Println("Registering application on hci0...")
	obj := app.Bus.Object("org.bluez", "/org/bluez/hci0")
	
	// Check if the object exists
	if !obj.Path().IsValid() {
		return fmt.Errorf("invalid object path: %s", obj.Path())
	}

	// Get the GattManager1 interface
	gattManager := obj.Call("org.bluez.GattManager1.RegisterApplication", 0, app.Path, map[string]interface{}{})
	if gattManager.Err != nil {
		log.Printf("D-Bus error details: %+v", gattManager.Err)
		return fmt.Errorf("failed to register application: %v", gattManager.Err)
	}
	log.Println("Application registered successfully")

	// Register advertisement on hci0
	log.Println("Registering advertisement on hci0...")
	advManager := obj.Call("org.bluez.LEAdvertisingManager1.RegisterAdvertisement", 0, app.Advertisement.Path, map[string]interface{}{})
	if advManager.Err != nil {
		log.Printf("D-Bus error details: %+v", advManager.Err)
		return fmt.Errorf("failed to register advertisement: %v", advManager.Err)
	}
	log.Println("Advertisement registered successfully")

	// Start background tasks
	log.Println("Starting background tasks...")
	go app.runHeartbeat()
	go app.runConnectionCheck()
	log.Println("Background tasks started")

	return nil
}

// RegisterApplication handles the GattManager1.RegisterApplication method
func (app *Application) RegisterApplication(path dbus.ObjectPath, options map[string]interface{}) error {
	log.Printf("RegisterApplication called with path: %s", path)
	return nil
}

// UnregisterApplication handles the GattManager1.UnregisterApplication method
func (app *Application) UnregisterApplication(path dbus.ObjectPath) error {
	log.Printf("UnregisterApplication called with path: %s", path)
	return nil
}

// Stop stops the application
func (app *Application) Stop() {
	close(app.StopChan)
}

// runHeartbeat sends periodic heartbeat messages
func (app *Application) runHeartbeat() {
	ticker := time.NewTicker(HEARTBEAT_INTERVAL)
	defer ticker.Stop()

	for {
		select {
		case <-app.StopChan:
			return
		case <-ticker.C:
			if app.Connected {
				heartbeat := []byte{MESSAGE_TYPE_PING}
				if err := app.Service.Characteristic.SendNotification(heartbeat); err != nil {
					log.Printf("Failed to send heartbeat: %v", err)
				}
			}
		}
	}
}

// runConnectionCheck checks for connected devices
func (app *Application) runConnectionCheck() {
	ticker := time.NewTicker(CONNECTION_CHECK_INTERVAL)
	defer ticker.Stop()

	for {
		select {
		case <-app.StopChan:
			return
		case <-ticker.C:
			obj := app.Bus.Object("org.bluez", "/org/bluez/hci0")
			devices, err := obj.GetProperty("org.bluez.Adapter1.Devices")
			if err != nil {
				log.Printf("Failed to get devices: %v", err)
				app.Connected = false
				continue
			}

			connected := len(devices.Value().([]dbus.ObjectPath)) > 0
			if connected != app.Connected {
				app.Connected = connected
				if connected {
					log.Println("Client connected")
				} else {
					log.Println("No clients connected")
				}
			}
		}
	}
}

// Implement D-Bus interface methods for Characteristic
func (c *Characteristic) GetAll(iface string) (map[string]dbus.Variant, error) {
	if iface == "org.bluez.GattCharacteristic1" {
		return c.GetProperties(), nil
	}
	return nil, fmt.Errorf("unknown interface: %s", iface)
}

func (c *Characteristic) Get(iface, prop string) (dbus.Variant, error) {
	props := c.GetProperties()
	if v, ok := props[prop]; ok {
		return v, nil
	}
	return dbus.Variant{}, fmt.Errorf("unknown property: %s", prop)
}

func (c *Characteristic) Set(iface, prop string, value dbus.Variant) error {
	return fmt.Errorf("property %s is read-only", prop)
}

func (c *Characteristic) GetDBusPath() dbus.ObjectPath {
	return c.Path
}

func (c *Characteristic) GetDBusInterface() string {
	return "org.bluez.GattCharacteristic1"
}

// Implement D-Bus interface methods for Service
func (s *Service) GetAll(iface string) (map[string]dbus.Variant, error) {
	if iface == "org.bluez.GattService1" {
		return s.GetProperties(), nil
	}
	return nil, fmt.Errorf("unknown interface: %s", iface)
}

func (s *Service) Get(iface, prop string) (dbus.Variant, error) {
	props := s.GetProperties()
	if v, ok := props[prop]; ok {
		return v, nil
	}
	return dbus.Variant{}, fmt.Errorf("unknown property: %s", prop)
}

func (s *Service) Set(iface, prop string, value dbus.Variant) error {
	return fmt.Errorf("property %s is read-only", prop)
}

func (s *Service) GetDBusPath() dbus.ObjectPath {
	return s.Path
}

func (s *Service) GetDBusInterface() string {
	return "org.bluez.GattService1"
}

// Implement D-Bus interface methods for Advertisement
func (a *Advertisement) GetAll(iface string) (map[string]dbus.Variant, error) {
	if iface == "org.bluez.LEAdvertisement1" {
		return a.GetProperties(), nil
	}
	return nil, fmt.Errorf("unknown interface: %s", iface)
}

func (a *Advertisement) Get(iface, prop string) (dbus.Variant, error) {
	props := a.GetProperties()
	if v, ok := props[prop]; ok {
		return v, nil
	}
	return dbus.Variant{}, fmt.Errorf("unknown property: %s", prop)
}

func (a *Advertisement) Set(iface, prop string, value dbus.Variant) error {
	return fmt.Errorf("property %s is read-only", prop)
}

func (a *Advertisement) GetDBusPath() dbus.ObjectPath {
	return a.Path
}

func (a *Advertisement) GetDBusInterface() string {
	return "org.bluez.LEAdvertisement1"
}

func main() {
	// Initialize logging with more detail
	log.SetFlags(log.LstdFlags | log.Lshortfile | log.Lmicroseconds)

	// Connect to the system bus
	log.Println("Connecting to system bus...")
	bus, err := dbus.SystemBus()
	if err != nil {
		log.Fatalf("Failed to connect to system bus: %v", err)
	}
	log.Println("Connected to system bus successfully")

	// Create and start the application
	log.Println("Creating application...")
	app := NewApplication(bus)
	if err := app.Start(); err != nil {
		log.Fatalf("Failed to start application: %v", err)
	}

	// Handle shutdown gracefully
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	<-sigChan
	log.Println("Shutting down...")
	app.Stop()
} 
