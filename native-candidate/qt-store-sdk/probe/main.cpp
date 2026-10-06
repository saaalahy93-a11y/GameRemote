#include <QtCore/qtversion.h>
#include <QtGui/qtgui-config.h>
#include <cstdio>

#if QT_VERSION != QT_VERSION_CHECK(6, 9, 3)
#error "The probe requires Qt 6.9.3."
#endif

#if !QT_CONFIG(appstore_compliant)
#error "Qt was not built with the appstore-compliant feature."
#endif

#ifndef QT_APPLE_NO_PRIVATE_APIS
#error "The Apple private API exclusion definition is missing."
#endif

#if !QT_CONFIG(vulkan)
#error "GameRemote requires QtGui and QtQuick built with Vulkan support."
#else
#include <QtGui/QVulkanInstance>
#include <QtGui/QWindow>
#include <QtQuick/QQuickGraphicsDevice>
#include <QtQuick/QQuickRenderTarget>

// Volatile addresses retain actual QtGui/QtQuick Vulkan symbol references at
// link time. The probe does not create an instance, device, window or GPU work.
auto volatile createVulkanInstance = &QVulkanInstance::create;
auto volatile setWindowVulkanInstance = &QWindow::setVulkanInstance;
auto volatile fromVulkanDeviceObjects = &QQuickGraphicsDevice::fromDeviceObjects;
auto volatile fromVulkanImage = static_cast<QQuickRenderTarget (*)(
    VkImage, VkImageLayout, const QSize &, int)>(&QQuickRenderTarget::fromVulkanImage);
#endif

int main()
{
    std::printf("Qt %s; appstore_compliant=%d; vulkan=%d; QT_APPLE_NO_PRIVATE_APIS defined\n",
                qVersion(), QT_FEATURE_appstore_compliant, QT_FEATURE_vulkan);
    return 0;
}
