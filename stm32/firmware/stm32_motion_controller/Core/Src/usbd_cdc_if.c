/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    usbd_cdc_if.c
  * @brief   CDC VCP interface for the STM32F411 chassis link. Hand-added.
  *          RX bytes are handed straight to rdk_comm_on_rx_bytes() (main.c),
  *          which feeds the rdk protocol parser -- the same path the old
  *          USART2 HAL_UART_RxCpltCallback used.
  ******************************************************************************
  */
/* USER CODE END Header */

#include "usbd_cdc_if.h"

/* Endpoint buffers. RX is one FS packet; TX is sized for our largest frame. */
static uint8_t UserRxBufferFS[APP_RX_DATA_SIZE];
static uint8_t UserTxBufferFS[APP_TX_DATA_SIZE];

extern USBD_HandleTypeDef hUsbDeviceFS;

static int8_t CDC_Init_FS(void);
static int8_t CDC_DeInit_FS(void);
static int8_t CDC_Control_FS(uint8_t cmd, uint8_t *pbuf, uint16_t length);
static int8_t CDC_Receive_FS(uint8_t *pbuf, uint32_t *Len);
static int8_t CDC_TransmitCplt_FS(uint8_t *pbuf, uint32_t *Len, uint8_t epnum);

USBD_CDC_ItfTypeDef USBD_Interface_fops_FS =
{
  CDC_Init_FS,
  CDC_DeInit_FS,
  CDC_Control_FS,
  CDC_Receive_FS,
  CDC_TransmitCplt_FS
};

/* Weak default so the USB library links even before main.c defines the strong
   version. main.c overrides this to feed the rdk parser. */
__weak void rdk_comm_on_rx_bytes(const uint8_t *data, uint32_t len)
{
  (void)data;
  (void)len;
}

static int8_t CDC_Init_FS(void)
{
  USBD_CDC_SetTxBuffer(&hUsbDeviceFS, UserTxBufferFS, 0);
  USBD_CDC_SetRxBuffer(&hUsbDeviceFS, UserRxBufferFS);
  return (USBD_OK);
}

static int8_t CDC_DeInit_FS(void)
{
  return (USBD_OK);
}

static int8_t CDC_Control_FS(uint8_t cmd, uint8_t *pbuf, uint16_t length)
{
  (void)pbuf;
  (void)length;
  switch (cmd)
  {
    case CDC_SEND_ENCAPSULATED_COMMAND:
    case CDC_GET_ENCAPSULATED_RESPONSE:
    case CDC_SET_COMM_FEATURE:
    case CDC_GET_COMM_FEATURE:
    case CDC_CLEAR_COMM_FEATURE:
    case CDC_SET_LINE_CODING:
    case CDC_GET_LINE_CODING:
    case CDC_SET_CONTROL_LINE_STATE:
    case CDC_SEND_BREAK:
    default:
      break;
  }
  return (USBD_OK);
}

static int8_t CDC_Receive_FS(uint8_t *pbuf, uint32_t *Len)
{
  rdk_comm_on_rx_bytes(pbuf, *Len);
  /* Re-arm reception on the next FS packet. */
  USBD_CDC_SetRxBuffer(&hUsbDeviceFS, &pbuf[0]);
  USBD_CDC_ReceivePacket(&hUsbDeviceFS);
  return (USBD_OK);
}

static int8_t CDC_TransmitCplt_FS(uint8_t *pbuf, uint32_t *Len, uint8_t epnum)
{
  (void)pbuf;
  (void)Len;
  (void)epnum;
  return (USBD_OK);
}

uint8_t CDC_Transmit_FS(uint8_t *Buf, uint16_t Len)
{
  USBD_CDC_HandleTypeDef *hcdc = (USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;
  if (hcdc == NULL)
  {
    return USBD_FAIL;
  }
  if (hcdc->TxState != 0)
  {
    return USBD_BUSY;
  }
  if (Len > APP_TX_DATA_SIZE)
  {
    Len = APP_TX_DATA_SIZE;
  }
  USBD_memcpy(UserTxBufferFS, Buf, Len);
  USBD_CDC_SetTxBuffer(&hUsbDeviceFS, UserTxBufferFS, Len);
  return USBD_CDC_TransmitPacket(&hUsbDeviceFS);
}
