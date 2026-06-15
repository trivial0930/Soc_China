/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    usbd_desc.h
  * @brief   USB device descriptors for the STM32F411 CDC VCP. Hand-added.
  ******************************************************************************
  */
/* USER CODE END Header */

#ifndef __USBD_DESC__H__
#define __USBD_DESC__H__

#ifdef __cplusplus
extern "C" {
#endif

#include "usbd_def.h"

#define DEVICE_ID1          (UID_BASE + 0x0U)
#define DEVICE_ID2          (UID_BASE + 0x4U)
#define DEVICE_ID3          (UID_BASE + 0x8U)

#define USB_SIZ_STRING_SERIAL       0x1AU

extern USBD_DescriptorsTypeDef FS_Desc;

#ifdef __cplusplus
}
#endif

#endif /* __USBD_DESC__H__ */
