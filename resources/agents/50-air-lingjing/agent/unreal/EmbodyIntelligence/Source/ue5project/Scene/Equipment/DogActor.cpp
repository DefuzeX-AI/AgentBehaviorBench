// Fill out your copyright notice in the Description page of Project Settings.

#include "DogActor.h"

ADogActor::ADogActor()
{
}

void ADogActor::SetDogScale(double InScale)
{
	SetEquipmentScale(FVector(InScale));
}

FSColor ADogActor::GetTagWidgetColor() const
{
	return FSColor(0, 26, 255, 0.5f);
}

FString ADogActor::GetImageSaveSubdir() const
{
	return TEXT("Dog");
}
