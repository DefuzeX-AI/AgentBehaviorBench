// Fill out your copyright notice in the Description page of Project Settings.

#include "DroneActor.h"

ADroneActor::ADroneActor()
{
}

FSColor ADroneActor::GetTagWidgetColor() const
{
	return FSColor(255, 179, 0, 0.5f);
}

FString ADroneActor::GetImageSaveSubdir() const
{
	return TEXT("Drone");
}
