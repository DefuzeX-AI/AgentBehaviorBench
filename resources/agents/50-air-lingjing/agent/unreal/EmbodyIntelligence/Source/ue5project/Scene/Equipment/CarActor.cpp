// Fill out your copyright notice in the Description page of Project Settings.

#include "CarActor.h"

ACarActor::ACarActor()
{
}

FSColor ACarActor::GetTagWidgetColor() const
{
	return FSColor(0, 179, 153, 0.5f);
}

FString ACarActor::GetImageSaveSubdir() const
{
	return TEXT("Car");
}
