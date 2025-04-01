package gatt_server

import (
	"fmt"
	"github.com/godbus/dbus/v5"
	"github.com/godbus/dbus/v5/introspect"
	"github.com/godbus/dbus/v5/prop"
)

const (
	DBusObjectPath = "/org/bluez/example"
	DBusInterface  = "org.bluez"
)

// InvalidArgsError represents an invalid arguments error
type InvalidArgsError struct {
	msg string
}

func (e *InvalidArgsError) Error() string {
	return e.msg
}

// Advertisement represents a BLE advertisement
type Advertisement struct {
	Path            dbus.ObjectPath
	Bus            *dbus.Conn
	Type           string
	ServiceUUIDs   []string
	ManufacturerData map[uint16][]byte
	SolicitUUIDs   []string
	ServiceData    map[string][]byte
	LocalName      string
	IncludeTxPower bool
}

// NewAdvertisement creates a new advertisement
func NewAdvertisement(bus *dbus.Conn, index int) *Advertisement {
	return &Advertisement{
		Path:            dbus.ObjectPath(fmt.Sprintf("%s/advertisement%d", DBusObjectPath, index)),
		Bus:            bus,
		Type:           "peripheral",
		IncludeTxPower: true,
	}
}

// GetProperties returns the advertisement properties
func (a *Advertisement) GetProperties() map[string]dbus.Variant {
	props := make(map[string]dbus.Variant)
	props["Type"] = dbus.MakeVariant(a.Type)
	
	if a.ServiceUUIDs != nil {
		props["ServiceUUIDs"] = dbus.MakeVariant(a.ServiceUUIDs)
	}
	if a.ManufacturerData != nil {
		props["ManufacturerData"] = dbus.MakeVariant(a.ManufacturerData)
	}
	if a.SolicitUUIDs != nil {
		props["SolicitUUIDs"] = dbus.MakeVariant(a.SolicitUUIDs)
	}
	if a.ServiceData != nil {
		props["ServiceData"] = dbus.MakeVariant(a.ServiceData)
	}
	if a.LocalName != "" {
		props["LocalName"] = dbus.MakeVariant(a.LocalName)
	}
	props["IncludeTxPower"] = dbus.MakeVariant(a.IncludeTxPower)
	
	return props
}

// Service represents a GATT service
type Service struct {
	Path           dbus.ObjectPath
	Bus           *dbus.Conn
	UUID          string
	Primary       bool
	Characteristics []*Characteristic
}

// NewService creates a new service
func NewService(bus *dbus.Conn, index int, uuid string, primary bool) *Service {
	return &Service{
		Path:     dbus.ObjectPath(fmt.Sprintf("%s/service%d", DBusObjectPath, index)),
		Bus:      bus,
		UUID:     uuid,
		Primary:  primary,
	}
}

// GetProperties returns the service properties
func (s *Service) GetProperties() map[string]dbus.Variant {
	props := make(map[string]dbus.Variant)
	props["UUID"] = dbus.MakeVariant(s.UUID)
	props["Primary"] = dbus.MakeVariant(s.Primary)
	
	paths := make([]dbus.ObjectPath, len(s.Characteristics))
	for i, chrc := range s.Characteristics {
		paths[i] = chrc.Path
	}
	props["Characteristics"] = dbus.MakeVariant(paths)
	
	return props
}

// Characteristic represents a GATT characteristic
type Characteristic struct {
	Path        dbus.ObjectPath
	Bus         *dbus.Conn
	UUID        string
	Service     *Service
	Flags       []string
	Descriptors []*Descriptor
	Value       []byte
	Notifying   bool
}

// NewCharacteristic creates a new characteristic
func NewCharacteristic(bus *dbus.Conn, index int, uuid string, service *Service, flags []string) *Characteristic {
	return &Characteristic{
		Path:    dbus.ObjectPath(fmt.Sprintf("%s/char%d", DBusObjectPath, index)),
		Bus:     bus,
		UUID:    uuid,
		Service: service,
		Flags:   flags,
	}
}

// GetProperties returns the characteristic properties
func (c *Characteristic) GetProperties() map[string]dbus.Variant {
	props := make(map[string]dbus.Variant)
	props["Service"] = dbus.MakeVariant(c.Service.Path)
	props["UUID"] = dbus.MakeVariant(c.UUID)
	props["Flags"] = dbus.MakeVariant(c.Flags)
	
	paths := make([]dbus.ObjectPath, len(c.Descriptors))
	for i, desc := range c.Descriptors {
		paths[i] = desc.Path
	}
	props["Descriptors"] = dbus.MakeVariant(paths)
	
	return props
}

// Descriptor represents a GATT descriptor
type Descriptor struct {
	Path           dbus.ObjectPath
	Bus            *dbus.Conn
	UUID           string
	Characteristic *Characteristic
	Flags          []string
	Value          []byte
}

// NewDescriptor creates a new descriptor
func NewDescriptor(bus *dbus.Conn, index int, uuid string, characteristic *Characteristic, flags []string) *Descriptor {
	return &Descriptor{
		Path:           dbus.ObjectPath(fmt.Sprintf("%s/desc%d", DBusObjectPath, index)),
		Bus:            bus,
		UUID:           uuid,
		Characteristic: characteristic,
		Flags:          flags,
	}
}

// GetProperties returns the descriptor properties
func (d *Descriptor) GetProperties() map[string]dbus.Variant {
	props := make(map[string]dbus.Variant)
	props["Characteristic"] = dbus.MakeVariant(d.Characteristic.Path)
	props["UUID"] = dbus.MakeVariant(d.UUID)
	props["Flags"] = dbus.MakeVariant(d.Flags)
	return props
}

// Application represents the main GATT application
type Application struct {
	Path      dbus.ObjectPath
	Bus       *dbus.Conn
	Services  []*Service
	Props     *prop.Properties
}

// NewApplication creates a new application
func NewApplication(bus *dbus.Conn) *Application {
	return &Application{
		Path: "/",
		Bus:  bus,
	}
}

// GetProperties returns the application properties
func (a *Application) GetProperties() map[string]dbus.Variant {
	props := make(map[string]dbus.Variant)
	
	paths := make([]dbus.ObjectPath, len(a.Services))
	for i, service := range a.Services {
		paths[i] = service.Path
	}
	props["Services"] = dbus.MakeVariant(paths)
	
	return props
}

// RegisterApplication registers the application with BlueZ
func (a *Application) RegisterApplication() error {
	obj := a.Bus.Object("org.bluez", "/org/bluez")
	call := obj.Call("org.bluez.GattManager1.RegisterApplication", 0, a.Path, map[string]interface{}{})
	return call.Err
}

// RegisterAdvertisement registers an advertisement with BlueZ
func (a *Advertisement) RegisterAdvertisement() error {
	obj := a.Bus.Object("org.bluez", "/org/bluez/hci0")
	call := obj.Call("org.bluez.LEAdvertisingManager1.RegisterAdvertisement", 0, a.Path, map[string]interface{}{})
	return call.Err
}

// SetupInterfaces sets up the D-Bus interfaces for all objects
func SetupInterfaces(bus *dbus.Conn, app *Application, adv *Advertisement) error {
	// Setup application
	if err := bus.Export(app, app.Path, "org.bluez.GattApplication1"); err != nil {
		return err
	}
	
	// Setup advertisement
	if err := bus.Export(adv, adv.Path, "org.bluez.LEAdvertisement1"); err != nil {
		return err
	}
	
	// Setup services
	for _, service := range app.Services {
		if err := bus.Export(service, service.Path, "org.bluez.GattService1"); err != nil {
			return err
		}
		
		// Setup characteristics
		for _, characteristic := range service.Characteristics {
			if err := bus.Export(characteristic, characteristic.Path, "org.bluez.GattCharacteristic1"); err != nil {
				return err
			}
			
			// Setup descriptors
			for _, descriptor := range characteristic.Descriptors {
				if err := bus.Export(descriptor, descriptor.Path, "org.bluez.GattDescriptor1"); err != nil {
					return err
				}
			}
		}
	}
	
	return nil
}

// SetupIntrospection sets up the D-Bus introspection for all objects
func SetupIntrospection(bus *dbus.Conn, app *Application, adv *Advertisement) error {
	// Setup application introspection
	if err := bus.Export(introspect.NewIntrospectable(app), app.Path, "org.freedesktop.DBus.Introspectable"); err != nil {
		return err
	}
	
	// Setup advertisement introspection
	if err := bus.Export(introspect.NewIntrospectable(adv), adv.Path, "org.freedesktop.DBus.Introspectable"); err != nil {
		return err
	}
	
	// Setup services introspection
	for _, service := range app.Services {
		if err := bus.Export(introspect.NewIntrospectable(service), service.Path, "org.freedesktop.DBus.Introspectable"); err != nil {
			return err
		}
		
		// Setup characteristics introspection
		for _, characteristic := range service.Characteristics {
			if err := bus.Export(introspect.NewIntrospectable(characteristic), characteristic.Path, "org.freedesktop.DBus.Introspectable"); err != nil {
				return err
			}
			
			// Setup descriptors introspection
			for _, descriptor := range characteristic.Descriptors {
				if err := bus.Export(introspect.NewIntrospectable(descriptor), descriptor.Path, "org.freedesktop.DBus.Introspectable"); err != nil {
					return err
				}
			}
		}
	}
	
	return nil
} 
